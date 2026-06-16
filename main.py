import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import sqlite3
import json
import qrcode
import datetime
import random
import string
import asyncio
from io import BytesIO
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO MASTER ---
TOKEN = os.getenv("TOKEN", "").strip()
ADMIN_IDS = [1385438838670889042, 1516532872050376844, 1488030839638986814]
BOT_NAME = "LW OMNI ULTIMATE"
EMBED_COLOR = 0x2b2d31
SUCCESS_COLOR = 0x00FF00
ERROR_COLOR = 0xFF0000

# --- GERADOR DE PIX PROFISSIONAL ---
class PixGenerator:
    def __init__(self, chave, valor, nome="VENDEDOR"):
        self.chave = chave; self.valor = f"{valor:.2f}"; self.nome = nome[:25]
    def _crc16(self, data):
        poly = 0x11021; res = 0xFFFF
        for b in data.encode('utf-8'):
            res ^= (b << 8)
            for _ in range(8):
                if (res & 0x8000): res = (res << 1) ^ poly
                else: res <<= 1
        return hex(res & 0xFFFF).upper()[2:].zfill(4)
    def generate(self):
        payload = ["000201", f"26{len(f'0014BR.GOV.BCB.PIX01{len(self.chave):02}{self.chave}'):02}0014BR.GOV.BCB.PIX01{len(self.chave):02}{self.chave}", "52040000", "5303986", f"54{len(self.valor):02}{self.valor}", "5802BR", f"59{len(self.nome):02}{self.nome}", "6008BRASILIA", "62070503***"]
        res = "".join(payload) + "6304"
        return res + self._crc16(res)

# --- BANCO DE DADOS RELACIONAL ---
def init_db():
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    # E-commerce
    c.execute('CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, desc TEXT, banner TEXT, category TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, prod_id TEXT, name TEXT, price REAL, stock TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, prod_name TEXT, plan_name TEXT, price REAL, date TEXT, status TEXT)')
    # Usuários e Economia
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, spent REAL DEFAULT 0, points INTEGER DEFAULT 0, rank TEXT DEFAULT "Iniciante", affiliates_count INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS deposits (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount REAL, status TEXT, date TEXT)')
    # Sistema
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, reason TEXT, date TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS tickets (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, channel_id INTEGER, status TEXT, type TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS feedbacks (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, stars INTEGER, comment TEXT, date TEXT)')
    conn.commit(); conn.close()

def db_query(q, p=(), f1=False, fa=False):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute(q, p)
    res = c.fetchone() if f1 else (c.fetchall() if fa else None)
    if not (f1 or fa): conn.commit()
    conn.close(); return res

# --- WEB SERVER ---
app = Flask(''); Thread(target=lambda: app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080))), daemon=True).start()
@app.route('/')
def home(): return "LW OMNI ULTIMATE IS LIVE!"

# --- BOT CORE ---
class LWBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        await self.tree.sync()

bot = LWBot()

# --- INTERFACES DE LUXO (COMPRA, SALDO, TICKET) ---

class TicketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
    @discord.ui.button(label="Abrir Suporte", style=discord.ButtonStyle.primary, emoji="🎫", custom_id="open_ticket")
    async def open_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Lógica de criação de canal de ticket
        guild = interaction.guild
        overwrites = {guild.default_role: discord.PermissionOverwrite(read_messages=False), interaction.user: discord.PermissionOverwrite(read_messages=True)}
        channel = await guild.create_text_channel(f"ticket-{interaction.user.name}", overwrites=overwrites)
        await interaction.response.send_message(f"✅ Ticket aberto em {channel.mention}", ephemeral=True)
        e = discord.Embed(title="🎫 Suporte LW", description=f"Olá {interaction.user.mention}, aguarde um administrador.", color=EMBED_COLOR)
        await channel.send(embed=e)

class FeedbackModal(discord.ui.Modal, title="Avaliar Compra"):
    stars = discord.ui.TextInput(label="Estrelas (1-5)", placeholder="5", min_length=1, max_length=1)
    comment = discord.ui.TextInput(label="Comentário", style=discord.TextStyle.paragraph, required=False)
    async def on_submit(self, interaction: discord.Interaction):
        db_query("INSERT INTO feedbacks (user_id, stars, comment, date) VALUES (?, ?, ?, ?)", 
                 (interaction.user.id, int(self.stars.value), self.comment.value, str(datetime.date.today())))
        await interaction.response.send_message("⭐ Obrigado pelo seu feedback!", ephemeral=True)

class PurchaseFlow(discord.ui.View):
    def __init__(self, plan_id, user_id):
        super().__init__(timeout=None); self.plan_id = plan_id; self.user_id = user_id

    @discord.ui.button(label="Pagar via PIX", style=discord.ButtonStyle.success, emoji="💳")
    async def pay_pix(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan = db_query("SELECT name, price FROM plans WHERE id=?", (self.plan_id,), f1=True)
        chave = db_query("SELECT value FROM config WHERE key='pix_key'", f1=True)
        pix = PixGenerator(chave[0] if chave else "ERRO", plan[1]); payload = pix.generate()
        qr = qrcode.make(payload); buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
        e = discord.Embed(title="💳 Pagamento Gerado", description=f"Valor: **R$ {plan[1]:.2f}**", color=0xFFFF00)
        e.add_field(name="Copia e Cola", value=f"```\n{payload}\n```")
        v = discord.ui.View()
        btn = discord.ui.Button(label="Confirmar Pagamento", style=discord.ButtonStyle.success)
        async def confirm(i):
            log_id = db_query("SELECT value FROM config WHERE key='log_channel'", f1=True)
            if log_id:
                chan = bot.get_channel(int(log_id[0]))
                if chan:
                    ev = discord.Embed(title="🔔 Pagamento em Análise", color=0x00AAFF)
                    ev.add_field(name="Cliente", value=f"{i.user.mention}"); ev.add_field(name="Produto", value=f"{plan[0]}")
                    vv = discord.ui.View(); b_apr = discord.ui.Button(label="Aprovar", style=discord.ButtonStyle.success)
                    async def apr(it):
                        stock = json.loads(db_query("SELECT stock FROM plans WHERE id=?", (self.plan_id,), f1=True)[0])
                        if not stock: return await it.response.send_message("❌ Sem estoque!", ephemeral=True)
                        item = stock.pop(0); db_query("UPDATE plans SET stock=? WHERE id=?", (json.dumps(stock), self.plan_id))
                        db_query("INSERT INTO sales (user_id, prod_name, plan_name, price, date, status) VALUES (?, ?, ?, ?, ?, ?)", (i.user.id, "Produto", plan[0], plan[1], str(datetime.date.today()), "Entregue"))
                        try: await i.user.send(f"✅ **Aprovado!**\n📦 **Item:**\n```\n{item}\n```"); await it.response.send_message("✅", ephemeral=True)
                        except: await it.response.send_message(f"❌ DM Fechada! {item}", ephemeral=True)
                    b_apr.callback = apr; vv.add_item(b_apr); await chan.send(embed=ev, view=vv)
            await i.response.send_message("✅ Enviado para análise!", ephemeral=True)
        btn.callback = confirm; v.add_item(btn)
        await interaction.followup.send(embed=e, file=discord.File(buf, "qr.png"), view=v, ephemeral=True)

class PlanSelect(discord.ui.Select):
    def __init__(self, prod_id):
        self.prod_id = prod_id
        plans = db_query("SELECT id, name, price, stock FROM plans WHERE prod_id=?", (prod_id,), fa=True)
        options = [discord.SelectOption(label=f"{p[1]}", value=str(p[0]), description=f"R$ {p[2]:.2f} - Estoque: {len(json.loads(p[3]))}", emoji="💎") for p in plans]
        super().__init__(placeholder="Selecione um plano...", options=options)
    async def callback(self, interaction: discord.Interaction):
        plan_id = int(self.values[0]); p = db_query("SELECT name, price FROM plans WHERE id=?", (plan_id,), f1=True)
        e = discord.Embed(title="🛒 Carrinho", description=f"Plano: **{p[0]}**\nValor: **R$ {p[1]:.2f}**", color=EMBED_COLOR)
        await interaction.response.send_message(embed=e, view=PurchaseFlow(plan_id, interaction.user.id), ephemeral=True)

class ProductView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None); self.add_item(PlanSelect(prod_id))

# --- COMANDOS OMNI ULTIMATE ---

@bot.tree.command(name="painel", description="[Admin] Painel Central")
async def painel(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    e = discord.Embed(title="👑 LW OMNI ULTIMATE - Central", color=SUCCESS_COLOR)
    v = discord.ui.View()
    b_pix = discord.ui.Button(label="Set PIX", style=discord.ButtonStyle.primary)
    async def px_cb(i):
        m = discord.ui.Modal(title="PIX"); inp = discord.ui.TextInput(label="Chave")
        async def s(it): db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (inp.value,)); await it.response.send_message("✅", ephemeral=True)
        m.add_item(inp); m.on_submit = s; await i.response.send_modal(m)
    b_pix.callback = px_cb; v.add_item(b_pix)
    
    b_log = discord.ui.Button(label="Set Logs", style=discord.ButtonStyle.primary)
    async def log_cb(i):
        m = discord.ui.Modal(title="Logs"); inp = discord.ui.TextInput(label="ID Canal")
        async def s(it): db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('log_channel', ?)", (inp.value,)); await it.response.send_message("✅", ephemeral=True)
        m.add_item(inp); m.on_submit = s; await i.response.send_modal(m)
    b_log.callback = log_cb; v.add_item(b_log)
    
    b_bc = discord.ui.Button(label="Broadcast", style=discord.ButtonStyle.danger)
    async def bc_cb(i):
        m = discord.ui.Modal(title="Massa"); msg = discord.ui.TextInput(label="Msg", style=discord.TextStyle.paragraph)
        async def s(it):
            users = db_query("SELECT user_id FROM users", fa=True)
            for u in users:
                try: user = await bot.fetch_user(u[0]); await user.send(msg.value)
                except: pass
            await it.response.send_message("✅", ephemeral=True)
        m.add_item(msg); m.on_submit = s; await i.response.send_modal(m)
    b_bc.callback = bc_cb; v.add_item(b_bc)
    
    await interaction.response.send_message(embed=e, view=v, ephemeral=True)

@bot.tree.command(name="criar", description="[Admin] Criar Produto")
async def criar(interaction: discord.Interaction):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    modal = discord.ui.Modal(title="Novo Produto")
    id_p = discord.ui.TextInput(label="ID"); nome = discord.ui.TextInput(label="Nome"); desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
    async def on_submit(it):
        db_query("INSERT OR REPLACE INTO products (id, name, desc) VALUES (?, ?, ?)", (id_p.value, nome.value, desc.value))
        await it.response.send_message("✅", ephemeral=True)
    modal.add_item(id_p); modal.add_item(nome); modal.add_item(desc); modal.on_submit = on_submit
    await interaction.response.send_modal(modal)

@bot.tree.command(name="vender", description="[Admin] Enviar Anúncio")
async def vender(interaction: discord.Interaction, id_produto: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    p = db_query("SELECT name, desc, banner FROM products WHERE id=?", (id_produto,), f1=True)
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    e = discord.Embed(title=f"🛒 {p[0]}", description=f"{p[1]}", color=EMBED_COLOR)
    if p[2]: e.set_image(url=p[2])
    await interaction.channel.send(embed=e, view=ProductView(id_produto))
    await interaction.response.send_message("✅", ephemeral=True)

@bot.tree.command(name="perfil", description="Ver meu perfil")
async def perfil(interaction: discord.Interaction):
    u = db_query("SELECT balance, spent, points, rank FROM users WHERE user_id=?", (interaction.user.id,), f1=True)
    if not u: db_query("INSERT INTO users (user_id) VALUES (?)", (interaction.user.id,)); u = (0, 0, 0, "Iniciante")
    e = discord.Embed(title=f"👤 Perfil", color=0x00AAFF)
    e.add_field(name="💰 Saldo", value=f"R$ {u[0]:.2f}"); e.add_field(name="🛒 Gasto", value=f"R$ {u[1]:.2f}"); e.add_field(name="⭐ Pontos", value=f"{u[2]}")
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="suporte", description="Abrir canal de suporte")
async def suporte(interaction: discord.Interaction):
    e = discord.Embed(title="🎫 Central de Suporte", description="Clique abaixo para abrir um ticket.", color=EMBED_COLOR)
    await interaction.channel.send(embed=e, view=TicketView())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

@bot.event
async def on_ready():
    init_db(); print(f"🚀 {bot.user.name} ULTIMATE ONLINE!")

bot.run(TOKEN)
