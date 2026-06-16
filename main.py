import discord
from discord import app_commands
from discord.ext import commands
import os
import sqlite3
import json
import requests
import qrcode
from io import BytesIO
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO ---
TOKEN = os.getenv("TOKEN", "").strip()
OWNER_ID = 1385438838670889042
GUILD_ID = 1516543103387828286
BOT_NAME = "LW ALUGUEL ULTRA"

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, price REAL, description TEXT, stock TEXT, banner TEXT, thumb TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit(); conn.close()

def get_db_val(table, key, col="value", key_col="key"):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute(f"SELECT {col} FROM {table} WHERE {key_col}=?", (key,))
    row = c.fetchone(); conn.close()
    return row[0] if row else None

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Ultra Online!"
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

# --- GERADOR DE PIX ROBUSTO (COM FALLBACK) ---
def get_pix_data(chave, valor, nome="VENDEDOR"):
    # Tenta usar a API estável primeiro
    try:
        url = f"https://api.geradornp.com.br/pix/gerar?chave={chave}&valor={valor}&nome={nome}&cidade=BRASIL"
        res = requests.get(url, timeout=5).json()
        if res.get("payload"):
            return res["payload"], res["qrcode"]
    except:
        pass
    
    # Se a API falhar, gera INTERNAMENTE (Copia e Cola Estático)
    # Formato simplificado do Banco Central
    payload = f"00020126360014BR.GOV.BCB.PIX0114{chave}5204000053039865404{valor:.2f}5802BR5908{nome[:25]}6008BRASILIA62070503***6304"
    return payload, None

# --- INTERFACES ---
class ProductManageView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None)
        self.prod_id = prod_id

    @discord.ui.button(label="Editar Preço", style=discord.ButtonStyle.secondary, emoji="💰")
    async def edit_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = discord.ui.Modal(title="Editar Preço")
        price_input = discord.ui.TextInput(label="Novo Preço", placeholder="ex: 25.00")
        async def on_submit(it):
            try:
                conn = sqlite3.connect('database.db'); c = conn.cursor()
                c.execute("UPDATE products SET price=? WHERE id=?", (float(price_input.value), self.prod_id))
                conn.commit(); conn.close()
                await it.response.send_message("✅ Preço atualizado!", ephemeral=True)
            except: await it.response.send_message("❌ Valor inválido.", ephemeral=True)
        modal.add_item(price_input); modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Add Estoque", style=discord.ButtonStyle.success, emoji="📦")
    async def add_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = discord.ui.Modal(title="Adicionar Estoque")
        stock_input = discord.ui.TextInput(label="Itens (um por linha)", style=discord.TextStyle.paragraph)
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("SELECT stock FROM products WHERE id=?", (self.prod_id,))
            current = json.loads(c.fetchone()[0])
            new_itens = stock_input.value.split('\n')
            current.extend([i for i in new_itens if i.strip()])
            c.execute("UPDATE products SET stock=? WHERE id=?", (json.dumps(current), self.prod_id))
            conn.commit(); conn.close()
            await it.response.send_message(f"✅ {len(new_itens)} itens adicionados!", ephemeral=True)
        modal.add_item(stock_input); modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

# --- COMANDOS ---
@bot.tree.command(name="painel", description="Painel Geral")
async def painel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    pix = get_db_val("config", "pix_key") or "NÃO CONFIGURADO"
    embed = discord.Embed(title=f"💎 Painel {BOT_NAME}", description=f"PIX: `{pix}`", color=0x00FF00)
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
    modal = discord.ui.Modal(title="Novo Produto")
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

@bot.tree.command(name="gerenciar", description="Gerenciar Produto")
async def gerenciar(interaction: discord.Interaction, id_produto: str):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    embed = discord.Embed(title=f"🛠️ Gerenciar: {p[0]}", description=f"Preço: R$ {p[1]:.2f} | Estoque: {len(json.loads(p[2]))}", color=0x00AAFF)
    await interaction.response.send_message(embed=embed, view=ProductManageView(id_produto), ephemeral=True)

@bot.tree.command(name="vender", description="Anunciar")
async def vender(interaction: discord.Interaction, id_produto: str):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, description, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    
    embed = discord.Embed(title=p[0], description=p[2], color=0x00FF00)
    embed.add_field(name="💰 Valor", value=f"```R$ {p[1]:.2f}```", inline=True)
    embed.add_field(name="📦 Estoque", value=f"```{len(json.loads(p[3]))}```", inline=True)
    
    view = discord.ui.View()
    btn = discord.ui.Button(label="Comprar", style=discord.ButtonStyle.success, emoji="🛒")
    async def buy_cb(i):
        chave = get_db_val("config", "pix_key")
        if not chave: return await i.response.send_message("❌ PIX não configurado.", ephemeral=True)
        
        payload, qr_url = get_pix_data(chave, p[1])
        
        e = discord.Embed(title="💳 Pagamento Gerado", color=0xFFFF00)
        e.add_field(name="Copia e Cola", value=f"```\n{payload}\n```")
        
        if qr_url:
            e.set_image(url=qr_url)
            await i.response.send_message(embed=e, ephemeral=True)
        else:
            # Fallback: Gera o QR Code internamente se a API falhar
            qr = qrcode.make(payload); buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            await i.response.send_message(embed=e, file=discord.File(buf, "qr.png"), ephemeral=True)
            
    btn.callback = buy_cb; view.add_item(btn)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"🚀 {bot.user.name} Online!")

bot.run(TOKEN)
