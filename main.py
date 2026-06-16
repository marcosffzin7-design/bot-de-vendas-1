import discord
from discord import app_commands
from discord.ext import commands
import os
import sqlite3
import json
import qrcode
import datetime
from io import BytesIO
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO ---
TOKEN = os.getenv("TOKEN", "").strip()
OWNER_ID = 1385438838670889042
GUILD_ID = 1516543103387828286
BOT_NAME = "LW ALUGUEL SUPREME"

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

# --- BANCO DE DADOS SUPREME ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    # Produtos e Planos
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, description TEXT, banner TEXT, thumb TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id TEXT, name TEXT, price REAL, stock TEXT)''')
    # Cupons
    cursor.execute('''CREATE TABLE IF NOT EXISTS coupons 
                      (code TEXT PRIMARY KEY, discount REAL, type TEXT)''') # type: percentage or fixed
    # Configurações e Logs
    cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    # Vendas
    cursor.execute('''CREATE TABLE IF NOT EXISTS sales 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, product_name TEXT, plan_name TEXT, price REAL, date TEXT)''')
    conn.commit(); conn.close()

def db_query(query, params=(), fetchone=False, fetchall=False):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute(query, params)
    res = None
    if fetchone: res = c.fetchone()
    elif fetchall: res = c.fetchall()
    else: conn.commit()
    conn.close()
    return res

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "LW SUPREME ONLINE!"
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

# --- INTERFACES SUPREME ---

class PlanSelectView(discord.ui.View):
    def __init__(self, product_id):
        super().__init__(timeout=None)
        self.product_id = product_id
        plans = db_query("SELECT id, name, price, stock FROM plans WHERE product_id=?", (product_id,), fetchall=True)
        for p in plans:
            stock_count = len(json.loads(p[3]))
            btn = discord.ui.Button(label=f"{p[1]} - R$ {p[2]:.2f} ({stock_count} em estoque)", 
                                    style=discord.ButtonStyle.secondary, custom_id=f"plan_{p[0]}", disabled=(stock_count == 0))
            btn.callback = self.make_callback(p)
            self.add_item(btn)

    def make_callback(self, plan):
        async def callback(interaction: discord.Interaction):
            chave = db_query("SELECT value FROM config WHERE key='pix_key'", fetchone=True)
            if not chave: return await interaction.response.send_message("❌ PIX não configurado.", ephemeral=True)
            
            pix = PixGenerator(chave[0], plan[2])
            payload = pix.generate()
            qr = qrcode.make(payload); buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            
            e = discord.Embed(title="💳 Pagamento Gerado", description=f"Produto: **{plan[1]}**\nValor: **R$ {plan[2]:.2f}**", color=0xFFFF00)
            e.add_field(name="Copia e Cola", value=f"```\n{payload}\n```")
            e.set_image(url="attachment://qr.png")
            
            view = discord.ui.View()
            confirm_btn = discord.ui.Button(label="Já Paguei / Enviar Comprovante", style=discord.ButtonStyle.success)
            async def confirm_cb(i):
                log_channel_id = db_query("SELECT value FROM config WHERE key='log_channel'", fetchone=True)
                if log_channel_id:
                    channel = bot.get_channel(int(log_channel_id[0]))
                    if channel:
                        await channel.send(f"🔔 **NOVA TENTATIVA DE COMPRA**\nUsuário: {i.user.mention}\nProduto: {plan[1]}\nValor: R$ {plan[2]:.2f}\n*Aguardando comprovante...*")
                await i.response.send_message("✅ Seu pedido foi enviado para análise. Envie o comprovante neste canal!", ephemeral=True)
            confirm_btn.callback = confirm_cb; view.add_item(confirm_btn)
            
            await interaction.response.send_message(embed=e, file=discord.File(buf, "qr.png"), view=view, ephemeral=True)
        return callback

class AdminManageView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None)
        self.prod_id = prod_id

    @discord.ui.button(label="Adicionar Plano", style=discord.ButtonStyle.primary, emoji="➕")
    async def add_plan(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = discord.ui.Modal(title="Novo Plano")
        name = discord.ui.TextInput(label="Nome do Plano (ex: Mensal)")
        price = discord.ui.TextInput(label="Preço (ex: 15.00)")
        async def on_submit(it):
            db_query("INSERT INTO plans (product_id, name, price, stock) VALUES (?, ?, ?, ?)", 
                     (self.prod_id, name.value, float(price.value), "[]"))
            await it.response.send_message("✅ Plano adicionado!", ephemeral=True)
        modal.add_item(name); modal.add_item(price); modal.on_submit = on_submit
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Gerenciar Estoque", style=discord.ButtonStyle.success, emoji="📦")
    async def manage_stock(self, interaction: discord.Interaction, button: discord.ui.Button):
        plans = db_query("SELECT id, name FROM plans WHERE product_id=?", (self.prod_id,), fetchall=True)
        if not plans: return await interaction.response.send_message("❌ Adicione um plano primeiro.", ephemeral=True)
        
        view = discord.ui.View()
        for p in plans:
            btn = discord.ui.Button(label=f"Estoque: {p[1]}", style=discord.ButtonStyle.secondary)
            async def cb(i, plan_id=p[0]):
                modal = discord.ui.Modal(title="Adicionar Itens")
                items = discord.ui.TextInput(label="Itens (um por linha)", style=discord.TextStyle.paragraph)
                async def sub(it):
                    current = json.loads(db_query("SELECT stock FROM plans WHERE id=?", (plan_id,), fetchone=True)[0])
                    new_list = items.value.split('\n')
                    current.extend([x for x in new_list if x.strip()])
                    db_query("UPDATE plans SET stock=? WHERE id=?", (json.dumps(current), plan_id))
                    await it.response.send_message(f"✅ {len(new_list)} itens adicionados!", ephemeral=True)
                modal.add_item(items); modal.on_submit = sub
                await i.response.send_modal(modal)
            btn.callback = cb; view.add_item(btn)
        await interaction.response.send_message("Escolha o plano para adicionar estoque:", view=view, ephemeral=True)

# --- COMANDOS SUPREME ---

@bot.tree.command(name="painel", description="Configurações Supreme")
async def painel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    pix = db_query("SELECT value FROM config WHERE key='pix_key'", fetchone=True)
    logs = db_query("SELECT value FROM config WHERE key='log_channel'", fetchone=True)
    
    embed = discord.Embed(title=f"👑 Dashboard Supreme - {BOT_NAME}", color=0x00FF00)
    embed.add_field(name="🔑 PIX", value=f"`{pix[0] if pix else 'N/A'}`")
    embed.add_field(name="📺 Canal Logs", value=f"<#{logs[0]}>" if logs else "`N/A`")
    
    view = discord.ui.View()
    b1 = discord.ui.Button(label="Set PIX", style=discord.ButtonStyle.primary)
    async def b1_cb(i):
        modal = discord.ui.Modal(title="PIX"); inp = discord.ui.TextInput(label="Chave")
        async def s(it): db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (inp.value,)); await it.response.send_message("✅", ephemeral=True)
        modal.add_item(inp); modal.on_submit = s; await i.response.send_modal(modal)
    b1.callback = b1_cb; view.add_item(b1)
    
    b2 = discord.ui.Button(label="Set Logs", style=discord.ButtonStyle.primary)
    async def b2_cb(i):
        modal = discord.ui.Modal(title="Logs"); inp = discord.ui.TextInput(label="ID do Canal")
        async def s(it): db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('log_channel', ?)", (inp.value,)); await it.response.send_message("✅", ephemeral=True)
        modal.add_item(inp); modal.on_submit = s; await i.response.send_modal(modal)
    b2.callback = b2_cb; view.add_item(b2)
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="criar", description="Criar Produto Supreme")
async def criar(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    modal = discord.ui.Modal(title="Novo Produto")
    id_p = discord.ui.TextInput(label="ID"); nome = discord.ui.TextInput(label="Nome")
    desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
    async def on_submit(it):
        db_query("INSERT OR REPLACE INTO products (id, name, description) VALUES (?, ?, ?)", (id_p.value, nome.value, desc.value))
        await it.response.send_message(f"✅ Produto {nome.value} criado! Agora use `/gerenciar` para adicionar planos.", ephemeral=True)
    modal.add_item(id_p); modal.add_item(nome); modal.add_item(desc); modal.on_submit = on_submit
    await interaction.response.send_modal(modal)

@bot.tree.command(name="gerenciar", description="Gerenciar Produto Supreme")
async def gerenciar(interaction: discord.Interaction, id_produto: str):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    p = db_query("SELECT name FROM products WHERE id=?", (id_produto,), fetchone=True)
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    
    plans = db_query("SELECT name, price FROM plans WHERE product_id=?", (id_produto,), fetchall=True)
    plan_text = "\n".join([f"🔹 {pl[0]}: R$ {pl[1]:.2f}" for pl in plans]) if plans else "Nenhum plano."
    
    embed = discord.Embed(title=f"🛠️ Gerenciando: {p[0]}", description=f"**Planos Ativos:**\n{plan_text}", color=0x00AAFF)
    await interaction.response.send_message(embed=embed, view=AdminManageView(id_produto), ephemeral=True)

@bot.tree.command(name="vender", description="Anunciar Produto Supreme")
async def vender(interaction: discord.Interaction, id_produto: str):
    p = db_query("SELECT name, description FROM products WHERE id=?", (id_produto,), fetchone=True)
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    
    embed = discord.Embed(title=f"✨ {p[0]}", description=p[1], color=0x00FF00)
    embed.set_footer(text=f"💎 {BOT_NAME} - Escolha um plano abaixo")
    
    await interaction.channel.send(embed=embed, view=PlanSelectView(id_produto))
    await interaction.response.send_message("✅ Anúncio Supreme enviado!", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"🚀 {bot.user.name} SUPREME ONLINE!")

bot.run(TOKEN)
