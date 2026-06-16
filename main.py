import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import sqlite3
import json
import qrcode
import datetime
import asyncio
from io import BytesIO
from flask import Flask
from threading import Thread

# --- CONFIGURAÇÃO MASTER ---
TOKEN = os.getenv("TOKEN", "").strip()
ADMIN_IDS = [1385438838670889042, 1516532872050376844, 1488030839638986814]
BOT_NAME = "LW OMNI ULTIMATE"
EMBED_COLOR = 0x2b2d31

# --- GERADOR DE PIX ---
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

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, desc TEXT, banner TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, prod_id TEXT, name TEXT, price REAL, stock TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0, spent REAL DEFAULT 0, points INTEGER DEFAULT 0)')
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS sales (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, prod_name TEXT, plan_name TEXT, price REAL, date TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS blacklist (user_id INTEGER PRIMARY KEY, reason TEXT)')
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
def home(): return "ONLINE!"

# --- BOT CORE ---
class LWBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        await self.tree.sync()

bot = LWBot()

# --- INTERFACES ---

class PurchaseFlow(discord.ui.View):
    def __init__(self, plan_id, user_id):
        super().__init__(timeout=None); self.plan_id = plan_id; self.user_id = user_id
    @discord.ui.button(label="Pagar via PIX", style=discord.ButtonStyle.success, emoji="💳")
    async def pay_pix(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan = db_query("SELECT name, price FROM plans WHERE id=?", (self.plan_id,), f1=True)
        chave = db_query("SELECT value FROM config WHERE key='pix_key'", f1=True)
        if not chave: return await interaction.followup.send("❌ PIX não configurado.", ephemeral=True)
        pix = PixGenerator(chave[0], plan[1]); payload = pix.generate()
        qr = qrcode.make(payload); buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
        e = discord.Embed(title="💳 Pagamento", description=f"Valor: R$ {plan[1]:.2f}", color=0xFFFF00)
        e.add_field(name="PIX Copia e Cola", value=f"```\n{payload}\n```")
        await interaction.followup.send(embed=e, file=discord.File(buf, "qr.png"), ephemeral=True)

class PlanSelect(discord.ui.Select):
    def __init__(self, prod_id):
        self.prod_id = prod_id
        plans = db_query("SELECT id, name, price, stock FROM plans WHERE prod_id=?", (prod_id,), fa=True)
        options = [discord.SelectOption(label=f"{p[1]}", value=str(p[0]), description=f"R$ {p[2]:.2f}", emoji="💎") for p in plans]
        super().__init__(placeholder="Selecione um plano...", options=options)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        plan_id = int(self.values[0]); p = db_query("SELECT name, price FROM plans WHERE id=?", (plan_id,), f1=True)
        e = discord.Embed(title="🛒 Carrinho", description=f"Plano: {p[0]}", color=EMBED_COLOR)
        await interaction.followup.send(embed=e, view=PurchaseFlow(plan_id, interaction.user.id), ephemeral=True)

class ProductView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None); self.add_item(PlanSelect(prod_id))

# --- COMANDOS ADMINISTRATIVOS ---

@bot.tree.command(name="criar_produto", description="[Admin] Criar um novo produto")
async def criar_produto(interaction: discord.Interaction, id: str, nome: str, descricao: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("INSERT OR REPLACE INTO products (id, name, desc) VALUES (?, ?, ?)", (id, nome, descricao))
    await interaction.response.send_message(f"✅ Produto `{nome}` criado!", ephemeral=True)

@bot.tree.command(name="deletar_produto", description="[Admin] Deletar um produto")
async def deletar_produto(interaction: discord.Interaction, id: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("DELETE FROM products WHERE id=?", (id,))
    db_query("DELETE FROM plans WHERE prod_id=?", (id,))
    await interaction.response.send_message(f"✅ Produto `{id}` e seus planos deletados!", ephemeral=True)

@bot.tree.command(name="add_plano", description="[Admin] Adicionar plano a um produto")
async def add_plano(interaction: discord.Interaction, id_produto: str, nome_plano: str, preco: float):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("INSERT INTO plans (prod_id, name, price, stock) VALUES (?, ?, ?, ?)", (id_produto, nome_plano, preco, json.dumps([])))
    await interaction.response.send_message(f"✅ Plano `{nome_plano}` adicionado ao produto `{id_produto}`!", ephemeral=True)

@bot.tree.command(name="add_estoque", description="[Admin] Adicionar itens ao estoque de um plano")
async def add_estoque(interaction: discord.Interaction, id_plano: int, itens: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    stock_data = db_query("SELECT stock FROM plans WHERE id=?", (id_plano,), f1=True)
    if not stock_data: return await interaction.response.send_message("❌ Plano não encontrado!", ephemeral=True)
    stock = json.loads(stock_data[0])
    novos_itens = itens.split(",")
    stock.extend([i.strip() for i in novos_itens])
    db_query("UPDATE plans SET stock=? WHERE id=?", (json.dumps(stock), id_plano))
    await interaction.response.send_message(f"✅ {len(novos_itens)} itens adicionados ao estoque!", ephemeral=True)

@bot.tree.command(name="limpar_estoque", description="[Admin] Limpar estoque de um plano")
async def limpar_estoque(interaction: discord.Interaction, id_plano: int):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("UPDATE plans SET stock=? WHERE id=?", (json.dumps([]), id_plano))
    await interaction.response.send_message("✅ Estoque limpo!", ephemeral=True)

@bot.tree.command(name="set_pix", description="[Admin] Configurar chave PIX")
async def set_pix(interaction: discord.Interaction, chave: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (chave,))
    await interaction.response.send_message(f"✅ Chave PIX configurada para: `{chave}`", ephemeral=True)

@bot.tree.command(name="set_logs", description="[Admin] Configurar canal de logs")
async def set_logs(interaction: discord.Interaction, id_canal: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('log_channel', ?)", (id_canal,))
    await interaction.response.send_message(f"✅ Canal de logs configurado!", ephemeral=True)

@bot.tree.command(name="broadcast", description="[Admin] Enviar mensagem para todos os usuários")
async def broadcast(interaction: discord.Interaction, mensagem: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    users = db_query("SELECT user_id FROM users", fa=True)
    count = 0
    for u in users:
        try:
            user = await bot.fetch_user(u[0])
            await user.send(mensagem)
            count += 1
        except: pass
    await interaction.followup.send(f"✅ Mensagem enviada para {count} usuários!", ephemeral=True)

@bot.tree.command(name="blacklist_add", description="[Admin] Adicionar usuário à blacklist")
async def blacklist_add(interaction: discord.Interaction, id_usuario: str, motivo: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    db_query("INSERT OR REPLACE INTO blacklist (user_id, reason) VALUES (?, ?)", (id_usuario, motivo))
    await interaction.response.send_message(f"✅ Usuário `{id_usuario}` banido!", ephemeral=True)

@bot.tree.command(name="vender", description="[Admin] Enviar anúncio de um produto")
async def vender(interaction: discord.Interaction, id_produto: str):
    if interaction.user.id not in ADMIN_IDS: return await interaction.response.send_message("❌", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    p = db_query("SELECT name, desc FROM products WHERE id=?", (id_produto,), f1=True)
    if not p: return await interaction.followup.send("❌ Produto não encontrado!", ephemeral=True)
    e = discord.Embed(title=f"🛒 {p[0]}", description=f"{p[1]}", color=EMBED_COLOR)
    await interaction.channel.send(embed=e, view=ProductView(id_produto))
    await interaction.followup.send("✅ Anúncio enviado!", ephemeral=True)

# --- COMANDOS DE USUÁRIO ---

@bot.tree.command(name="perfil", description="Ver meu perfil")
async def perfil(interaction: discord.Interaction):
    u = db_query("SELECT balance, spent, points FROM users WHERE user_id=?", (interaction.user.id,), f1=True)
    if not u: db_query("INSERT INTO users (user_id) VALUES (?)", (interaction.user.id,)); u = (0, 0, 0)
    e = discord.Embed(title=f"👤 Perfil", color=0x00AAFF)
    e.add_field(name="💰 Saldo", value=f"R$ {u[0]:.2f}"); e.add_field(name="🛒 Gasto", value=f"R$ {u[1]:.2f}"); e.add_field(name="⭐ Pontos", value=f"{u[2]}")
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.tree.command(name="rank", description="Ver ranking de compradores")
async def rank(interaction: discord.Interaction):
    top = db_query("SELECT user_id, spent FROM users ORDER BY spent DESC LIMIT 10", fa=True)
    e = discord.Embed(title="🏆 Ranking de Compradores", color=0xFFD700)
    for i, u in enumerate(top): e.add_field(name=f"{i+1}º Lugar", value=f"<@{u[0]}> - R$ {u[1]:.2f}", inline=False)
    await interaction.response.send_message(embed=e, ephemeral=True)

@bot.event
async def on_ready():
    init_db(); print(f"🚀 {bot.user.name} ONLINE!")

bot.run(TOKEN)
