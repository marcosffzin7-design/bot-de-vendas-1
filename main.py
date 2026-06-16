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
# LISTA DE ADMINISTRADORES (Adicione os IDs aqui)
ADMIN_IDS = [1385438838670889042, 1516532872050376844, 1488030839638986814] # Lista de administradores atualizada
BOT_NAME = "LW ALUGUEL MAGNATE"
EMBED_COLOR = 0x2b2d31

# --- GERADOR DE PIX OFICIAL ---
class PixGenerator:
    def __init__(self, chave, valor, nome="VENDEDOR"):
        self.chave = chave
        self.valor = f"{valor:.2f}"
        self.nome = nome[:25]

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
            "52040000", "5303986", f"54{len(self.valor):02}{self.valor}", "5802BR",
            f"59{len(self.nome):02}{self.nome}", "6008BRASILIA", "62070503***"
        ]
        res = "".join(payload) + "6304"
        return res + self._crc16(res)

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS products (id TEXT PRIMARY KEY, name TEXT, desc TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, prod_id TEXT, name TEXT, price REAL, stock TEXT)')
    c.execute('CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT)')
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
def home(): return "MAGNATE ONLINE!"

# --- BOT ---
class LWBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all())
    async def setup_hook(self):
        await self.tree.sync()

bot = LWBot()

def is_admin(user_id):
    return user_id in ADMIN_IDS

# --- INTERFACE (SELECT MENU) ---
class PlanSelect(discord.ui.Select):
    def __init__(self, prod_id):
        self.prod_id = prod_id
        plans = db_query("SELECT id, name, price, stock FROM plans WHERE prod_id=?", (prod_id,), fa=True)
        options = [discord.SelectOption(label=f"{p[1]}", value=str(p[0]), description=f"R$ {p[2]:.2f} - Estoque: {len(json.loads(p[3]))}", emoji="📦") for p in plans]
        super().__init__(placeholder="Selecione o plano desejado...", options=options, custom_id="select_plan")

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        plan_id = int(self.values[0])
        p = db_query("SELECT name, price, stock FROM plans WHERE id=?", (plan_id,), f1=True)
        prod = db_query("SELECT name, desc FROM products WHERE id=?", (self.prod_id,), f1=True)
        embed = discord.Embed(title=f"🛒 {prod[0]}", description=f"{prod[1]}\n\n**Plano:** `{p[0]}`\n**Valor:** `R$ {p[1]:.2f}`\n**Estoque:** `{len(json.loads(p[2]))}`", color=EMBED_COLOR)
        view = discord.ui.View(); view.add_item(PlanSelect(self.prod_id))
        btn_buy = discord.ui.Button(label="Comprar Agora", style=discord.ButtonStyle.success, emoji="💳")
        async def buy_cb(i):
            await i.response.defer(ephemeral=True, thinking=True)
            chave = db_query("SELECT value FROM config WHERE key='pix_key'", f1=True)
            if not chave: return await i.followup.send("❌ PIX não configurado.", ephemeral=True)
            pix = PixGenerator(chave[0], p[1]); payload = pix.generate()
            qr = qrcode.make(payload); buf = BytesIO(); qr.save(buf, format="PNG"); buf.seek(0)
            e = discord.Embed(title="💳 Pagamento Gerado", description=f"Pague **R$ {p[1]:.2f}** para receber seu produto.", color=0xFFFF00)
            e.add_field(name="PIX Copia e Cola", value=f"```\n{payload}\n```")
            await i.followup.send(embed=e, file=discord.File(buf, "qr.png"), ephemeral=True)
        btn_buy.callback = buy_cb; view.add_item(btn_buy)
        await interaction.edit_original_response(embed=embed, view=view)

class ProductView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None)
        self.add_item(PlanSelect(prod_id))

# --- COMANDOS ---
@bot.tree.command(name="criar", description="Criar Produto (Admin)")
async def criar(interaction: discord.Interaction):
    if not is_admin(interaction.user.id): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    modal = discord.ui.Modal(title="Novo Produto")
    id_p = discord.ui.TextInput(label="ID"); nome = discord.ui.TextInput(label="Nome"); desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
    async def on_submit(it):
        db_query("INSERT OR REPLACE INTO products (id, name, desc) VALUES (?, ?, ?)", (id_p.value, nome.value, desc.value))
        await it.response.send_message("✅ Criado!", ephemeral=True)
    modal.add_item(id_p); modal.add_item(nome); modal.add_item(desc); modal.on_submit = on_submit
    await interaction.response.send_modal(modal)

@bot.tree.command(name="vender", description="Anunciar Produto (Admin)")
async def vender(interaction: discord.Interaction, id_produto: str):
    if not is_admin(interaction.user.id): return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    p = db_query("SELECT name, desc FROM products WHERE id=?", (id_produto,), f1=True)
    if not p: return await interaction.followup.send("❌ Produto não encontrado.", ephemeral=True)
    embed = discord.Embed(title=f"🛒 {p[0]}", description=f"{p[1]}\n\n*Selecione um plano abaixo para ver detalhes e comprar.*", color=EMBED_COLOR)
    await interaction.channel.send(embed=embed, view=ProductView(id_produto))
    await interaction.followup.send("✅ Anúncio enviado!", ephemeral=True)

@bot.tree.command(name="painel", description="Configurações (Admin)")
async def painel(interaction: discord.Interaction):
    if not is_admin(interaction.user.id): return await interaction.response.send_message("❌", ephemeral=True)
    pix = db_query("SELECT value FROM config WHERE key='pix_key'", f1=True)
    embed = discord.Embed(title="⚙️ Painel", description=f"PIX: `{pix[0] if pix else 'N/A'}`", color=0x00FF00)
    btn = discord.ui.Button(label="Set PIX", style=discord.ButtonStyle.primary)
    async def cb(i):
        modal = discord.ui.Modal(title="PIX"); inp = discord.ui.TextInput(label="Chave")
        async def s(it): db_query("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (inp.value,)); await it.response.send_message("✅", ephemeral=True)
        modal.add_item(inp); modal.on_submit = s; await i.response.send_modal(modal)
    btn.callback = cb; view = discord.ui.View(); view.add_item(btn)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="gerenciar", description="Gerenciar Produto (Admin)")
async def gerenciar(interaction: discord.Interaction, id_produto: str):
    if not is_admin(interaction.user.id): return await interaction.response.send_message("❌", ephemeral=True)
    p = db_query("SELECT name FROM products WHERE id=?", (id_produto,), f1=True)
    if not p: return await interaction.response.send_message("❌", ephemeral=True)
    view = discord.ui.View()
    btn_plan = discord.ui.Button(label="Add Plano", style=discord.ButtonStyle.primary); btn_stock = discord.ui.Button(label="Add Estoque", style=discord.ButtonStyle.success)
    async def plan_cb(i):
        modal = discord.ui.Modal(title="Novo Plano"); n = discord.ui.TextInput(label="Nome"); pr = discord.ui.TextInput(label="Preço")
        async def s(it): db_query("INSERT INTO plans (prod_id, name, price, stock) VALUES (?, ?, ?, ?)", (id_produto, n.value, float(pr.value), "[]")); await it.response.send_message("✅", ephemeral=True)
        modal.add_item(n); modal.add_item(pr); modal.on_submit = s; await i.response.send_modal(modal)
    btn_plan.callback = plan_cb; view.add_item(btn_plan)
    async def stock_cb(i):
        plans = db_query("SELECT id, name FROM plans WHERE prod_id=?", (id_produto,), fa=True)
        v = discord.ui.View()
        for pl in plans:
            b = discord.ui.Button(label=f"Add: {pl[1]}", style=discord.ButtonStyle.secondary)
            async def sub_cb(it, pid=pl[0]):
                modal = discord.ui.Modal(title="Itens"); inp = discord.ui.TextInput(label="Itens", style=discord.TextStyle.paragraph)
                async def sub_s(itt):
                    curr = json.loads(db_query("SELECT stock FROM plans WHERE id=?", (pid,), f1=True)[0])
                    new_i = inp.value.split('\n'); curr.extend([x for x in new_i if x.strip()])
                    db_query("UPDATE plans SET stock=? WHERE id=?", (json.dumps(curr), pid)); await itt.response.send_message("✅", ephemeral=True)
                modal.add_item(inp); modal.on_submit = sub_s; await it.response.send_modal(modal)
            b.callback = sub_cb; v.add_item(b)
        await i.response.send_message("Escolha o plano:", view=v, ephemeral=True)
    btn_stock.callback = stock_cb; view.add_item(btn_stock)
    await interaction.response.send_message(f"🛠️ Gerenciando: {p[0]}", view=view, ephemeral=True)

@bot.event
async def on_ready():
    init_db(); print(f"🚀 {bot.user.name} ONLINE!")

bot.run(TOKEN)
