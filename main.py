import discord
from discord import app_commands
from discord.ext import commands
import os
import json
import sqlite3
import qrcode
from io import BytesIO
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO ---
TOKEN = os.getenv("TOKEN")
OWNER_ID = 1385438838670889042
BOT_NAME = "LW ALUGUEL ULTRA"
EMBED_COLOR = 0x00FF00

# --- BANCO DE DADOS (SQLite para estabilidade total) ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, price REAL, description TEXT, stock TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

def get_pix_key():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM config WHERE key='pix_key'")
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else "NÃO CONFIGURADO"

# --- WEB SERVER (KEEP ALIVE) ---
server = Flask('')
@server.route('/')
def home(): return "Bot Ultra Online!"
def run(): server.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)))
Thread(target=run).start()

# --- BOT ---
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("🔄 Sincronizando comandos Slash...")
        await self.tree.sync()

bot = MyBot()

# --- MODAIS ---
class PixModal(discord.ui.Modal, title="Configurar PIX"):
    chave = discord.ui.TextInput(label="Sua Chave PIX", placeholder="Digite aqui...", required=True)
    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (self.chave.value,))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"✅ Chave PIX atualizada!", ephemeral=True)

class ProductModal(discord.ui.Modal, title="Novo Produto Ultra"):
    id_p = discord.ui.TextInput(label="ID do Produto", placeholder="ex: nitro")
    nome = discord.ui.TextInput(label="Nome", placeholder="ex: Discord Nitro")
    preco = discord.ui.TextInput(label="Preço", placeholder="ex: 15.00")
    desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        conn = sqlite3.connect('database.db')
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO products (id, name, price, description, stock) VALUES (?, ?, ?, ?, ?)",
                       (self.id_p.value, self.nome.value, float(self.preco.value), self.desc.value, "[]"))
        conn.commit()
        conn.close()
        await interaction.response.send_message(f"✅ Produto **{self.nome.value}** criado!", ephemeral=True)

# --- COMANDOS SLASH ---
@bot.tree.command(name="painel", description="Painel de Controle Ultra")
async def painel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    
    embed = discord.Embed(title=f"💎 {BOT_NAME} - Painel", color=EMBED_COLOR)
    embed.add_field(name="🔑 PIX", value=f"`{get_pix_key()}`")
    
    view = discord.ui.View()
    btn_pix = discord.ui.Button(label="Configurar PIX", style=discord.ButtonStyle.primary)
    btn_pix.callback = lambda i: i.response.send_modal(PixModal())
    view.add_item(btn_pix)
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="criar", description="Criar um produto profissional")
async def criar(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.send_modal(ProductModal())

@bot.tree.command(name="vender", description="Enviar anúncio de venda")
async def vender(interaction: discord.Interaction, id_produto: str):
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute("SELECT name, price, description, stock FROM products WHERE id=?", (id_produto,))
    p = cursor.fetchone()
    conn.close()
    
    if not p: return await interaction.response.send_message("❌ Não encontrado.", ephemeral=True)
    
    estoque = json.loads(p[3])
    embed = discord.Embed(title=p[0], description=p[2], color=EMBED_COLOR)
    embed.add_field(name="💰 Preço", value=f"R$ {p[1]:.2f}")
    embed.add_field(name="📦 Estoque", value=f"{len(estoque)}")
    
    view = discord.ui.View()
    buy_btn = discord.ui.Button(label="Comprar", style=discord.ButtonStyle.success, emoji="🛒")
    
    async def buy_callback(i: discord.Interaction):
        pix_key = get_pix_key()
        if pix_key == "NÃO CONFIGURADO": return await i.response.send_message("❌ Erro no PIX.", ephemeral=True)
        
        pix_code = f"00020126360014BR.GOV.BCB.PIX0114{pix_key}5204000053039865404{p[1]:.2f}5802BR5908VENDEDOR6008BRASILIA62070503***6304"
        qr = qrcode.make(pix_code)
        buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
        
        pay_embed = discord.Embed(title="Pagamento PIX", description=f"Valor: R$ {p[1]:.2f}", color=0xFFFF00)
        pay_embed.add_field(name="Copia e Cola", value=f"```\n{pix_code}\n```")
        await i.response.send_message(embed=pay_embed, file=discord.File(buf, "qr.png"), ephemeral=True)
        
    buy_btn.callback = buy_callback
    view.add_item(buy_btn)
    
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Enviado!", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"✅ {bot.user} Online!")

if __name__ == "__main__":
    bot.run(TOKEN)
