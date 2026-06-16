import discord
from discord import app_commands
from discord.ext import commands
import os
import sqlite3
import json
import qrcode
from io import BytesIO
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO ---
TOKEN = os.getenv("TOKEN", "").strip()
OWNER_ID = 1385438838670889042
GUILD_ID = 1516543103387828286
BOT_NAME = "LW ALUGUEL ULTRA"

# --- GERADOR DE PIX OFICIAL (CRC16/EMV) ---
class PixGenerator:
    def __init__(self, chave, valor, nome="VENDEDOR", cidade="BRASILIA"):
        self.chave = chave
        self.valor = f"{valor:.2f}"
        self.nome = nome[:25]
        self.cidade = cidade[:15]

    def _crc16(self, data):
        poly = 0x11021
        res = 0xFFFF
        for b in data.encode('utf-8'):
            res ^= (b << 8)
            for _ in range(8):
                if (res & 0x8000): res = (res << 1) ^ poly
                else: res <<= 1
        return hex(res & 0xFFFF).upper()[2:].zfill(4)

    def generate(self):
        payload = [
            "000201",
            f"26{len(f'0014BR.GOV.BCB.PIX01{len(self.chave):02}{self.chave}'):02}0014BR.GOV.BCB.PIX01{len(self.chave):02}{self.chave}",
            "52040000",
            "5303986",
            f"54{len(self.valor):02}{self.valor}",
            "5802BR",
            f"59{len(self.nome):02}{self.nome}",
            f"60{len(self.cidade):02}{self.cidade}",
            "62070503***"
        ]
        res = "".join(payload) + "6304"
        return res + self._crc16(res)

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, price REAL, description TEXT, stock TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit(); conn.close()

def get_db_val(key):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT value FROM config WHERE key=?", (key,))
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

# --- INTERFACE DE LUXO ---
class ProductManageView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None)
        self.prod_id = prod_id

    @discord.ui.button(label="Alterar Preço", style=discord.ButtonStyle.secondary, emoji="💸")
    async def edit_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = discord.ui.Modal(title="Novo Preço")
        price = discord.ui.TextInput(label="Valor (ex: 10.00)")
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("UPDATE products SET price=? WHERE id=?", (float(price.value), self.prod_id))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Valor atualizado!", ephemeral=True)
        modal.add_item(price); modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Gerenciar Estoque", style=discord.ButtonStyle.success, emoji="📦")
    async def add_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = discord.ui.Modal(title="Adicionar Estoque")
        stock = discord.ui.TextInput(label="Itens (um por linha)", style=discord.TextStyle.paragraph)
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("SELECT stock FROM products WHERE id=?", (self.prod_id,))
            current = json.loads(c.fetchone()[0])
            new_itens = stock.value.split('\n')
            current.extend([i for i in new_itens if i.strip()])
            c.execute("UPDATE products SET stock=? WHERE id=?", (json.dumps(current), self.prod_id))
            conn.commit(); conn.close()
            await it.response.send_message(f"✅ {len(new_itens)} itens adicionados!", ephemeral=True)
        modal.add_item(stock); modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

# --- COMANDOS ---
@bot.tree.command(name="painel", description="Configurações do Bot")
async def painel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    pix = get_db_val("pix_key") or "NÃO CONFIGURADO"
    embed = discord.Embed(title=f"💎 Central {BOT_NAME}", description=f"Sua Chave PIX: `{pix}`", color=0x00FF00)
    view = discord.ui.View()
    btn = discord.ui.Button(label="Mudar Chave PIX", style=discord.ButtonStyle.primary, emoji="🔑")
    async def set_pix(i):
        modal = discord.ui.Modal(title="Configurar PIX")
        input_pix = discord.ui.TextInput(label="Chave PIX (CPF, E-mail ou Aleatória)")
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (input_pix.value,))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Chave PIX salva!", ephemeral=True)
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
        await it.response.send_message("✅ Produto Criado!", ephemeral=True)
    for item in [id_p, nome, preco, desc]: modal.add_item(item)
    modal.on_submit = on_submit; await interaction.response.send_modal(modal)

@bot.tree.command(name="gerenciar", description="Gerenciar Produto")
async def gerenciar(interaction: discord.Interaction, id_produto: str):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    embed = discord.Embed(title=f"🛠️ Gerenciando: {p[0]}", description=f"💰 Preço: R$ {p[1]:.2f}\n📦 Estoque: {len(json.loads(p[2]))} itens", color=0x00AAFF)
    await interaction.response.send_message(embed=embed, view=ProductManageView(id_produto), ephemeral=True)

@bot.tree.command(name="vender", description="Anunciar Produto")
async def vender(interaction: discord.Interaction, id_produto: str):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, description, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    
    embed = discord.Embed(title=f"🛒 {p[0]}", description=p[2], color=0x00FF00)
    embed.add_field(name="💰 Valor", value=f"```R$ {p[1]:.2f}```", inline=True)
    embed.add_field(name="📦 Estoque", value=f"```{len(json.loads(p[3]))}```", inline=True)
    embed.set_footer(text=f"© {BOT_NAME} - Compra Segura")
    
    view = discord.ui.View()
    btn = discord.ui.Button(label="Comprar Agora", style=discord.ButtonStyle.success, emoji="💳")
    async def buy(i):
        chave = get_db_val("pix_key")
        if not chave: return await i.response.send_message("❌ Configure o PIX no /painel", ephemeral=True)
        
        # Gerando PIX Real (EMV/CRC16)
        pix = PixGenerator(chave, p[1])
        payload = pix.generate()
        
        qr = qrcode.make(payload); buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
        
        e = discord.Embed(title="💳 Pagamento Gerado", description=f"Valor: **R$ {p[1]:.2f}**\n\nCopie o código abaixo e pague no seu banco:", color=0xFFFF00)
        e.add_field(name="Copia e Cola", value=f"```\n{payload}\n```")
        e.set_image(url="attachment://qr.png")
        await i.response.send_message(embed=e, file=discord.File(buf, "qr.png"), ephemeral=True)
        
    btn.callback = buy; view.add_item(btn)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Anúncio enviado!", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"🚀 {bot.user.name} ONLINE com PIX Real!")

bot.run(TOKEN)
