import discord
from discord import app_commands
from discord.ext import commands
import os
import sqlite3
import json
import requests
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO ---
TOKEN = os.getenv("TOKEN", "").strip()
OWNER_ID = 1385438838670889042
GUILD_ID = 1516543103387828286
BOT_NAME = "LW ALUGUEL ULTRA"
EMBED_COLOR = 0x00FF00

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, price REAL, description TEXT, stock TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit(); conn.close()

def get_pix_key():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key='pix_key'")
    row = cursor.fetchone(); conn.close()
    return row[0] if row else "NÃO CONFIGURADO"

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online!"
Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080))), daemon=True).start()

# --- BOT ---
class LWBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        guild = discord.Object(id=GUILD_ID)
        self.tree.copy_global_to(guild=guild)
        await self.tree.sync(guild=guild)

bot = LWBot()

# --- GERADOR DE PIX (API) ---
def generate_pix(chave, valor, nome_loja):
    # Usando a API gratuita da OpenPIX/GeradorPix para garantir validade
    url = f"https://api.geradornp.com.br/pix/gerar?chave={chave}&valor={valor}&nome={nome_loja}&cidade=BRASIL"
    try:
        response = requests.get(url)
        data = response.json()
        return data.get("payload"), data.get("qrcode") # Retorna Copia e Cola e Link da Imagem
    except:
        return None, None

# --- COMANDOS ---
@bot.tree.command(name="painel", description="Configurações")
async def painel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    embed = discord.Embed(title="⚙️ Painel", description=f"PIX: `{get_pix_key()}`", color=EMBED_COLOR)
    view = discord.ui.View()
    btn = discord.ui.Button(label="Configurar PIX", style=discord.ButtonStyle.primary)
    async def set_pix(i):
        modal = discord.ui.Modal(title="Configurar PIX")
        input_pix = discord.ui.TextInput(label="Chave PIX")
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (input_pix.value,))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Atualizado!", ephemeral=True)
        modal.add_item(input_pix); modal.on_submit = on_submit
        await i.response.send_modal(modal)
    btn.callback = set_pix; view.add_item(btn)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="criar", description="Criar Produto")
async def criar(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    modal = discord.ui.Modal(title="Criar Produto")
    id_p = discord.ui.TextInput(label="ID"); nome = discord.ui.TextInput(label="Nome")
    preco = discord.ui.TextInput(label="Preço"); desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
    async def on_submit(it):
        conn = sqlite3.connect('database.db'); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO products (id, name, price, description, stock) VALUES (?, ?, ?, ?, ?)",
                   (id_p.value, nome.value, float(preco.value), desc.value, "[]"))
        conn.commit(); conn.close()
        await it.response.send_message("✅ Criado!", ephemeral=True)
    for item in [id_p, nome, preco, desc]: modal.add_item(item)
    modal.on_submit = on_submit; await interaction.response.send_modal(modal)

@bot.tree.command(name="vender", description="Anunciar")
async def vender(interaction: discord.Interaction, id_produto: str):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, description, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    
    embed = discord.Embed(title=p[0], description=p[2], color=EMBED_COLOR)
    embed.add_field(name="💰 Preço", value=f"R$ {p[1]:.2f}")
    
    view = discord.ui.View()
    btn = discord.ui.Button(label="Comprar", style=discord.ButtonStyle.success, emoji="🛒")
    async def buy(i):
        chave = get_pix_key()
        if chave == "NÃO CONFIGURADO": return await i.response.send_message("❌ Configure o PIX no /painel", ephemeral=True)
        
        # Gerando PIX via API Profissional
        payload, qr_url = generate_pix(chave, p[1], "LW_ALUGUEL")
        
        if not payload: return await i.response.send_message("❌ Erro ao gerar PIX. Verifique sua chave.", ephemeral=True)
        
        e = discord.Embed(title="Pagamento PIX", description=f"Valor: R$ {p[1]:.2f}", color=0xFFFF00)
        e.add_field(name="Copia e Cola", value=f"```\n{payload}\n```")
        e.set_image(url=qr_url)
        await i.response.send_message(embed=e, ephemeral=True)
        
    btn.callback = buy; view.add_item(btn)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"🚀 {bot.user.name} Online!")

bot.run(TOKEN)
