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

# --- INTERFACES ROBUSTAS ---

class ProductManageView(discord.ui.View):
    def __init__(self, prod_id):
        super().__init__(timeout=None)
        self.prod_id = prod_id

    @discord.ui.button(label="Editar Preço", style=discord.ButtonStyle.secondary, emoji="💰")
    async def edit_price(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = discord.ui.Modal(title="Editar Preço")
        price_input = discord.ui.TextInput(label="Novo Preço", placeholder="ex: 25.00")
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("UPDATE products SET price=? WHERE id=?", (float(price_input.value), self.prod_id))
            conn.commit(); conn.close()
            await it.response.send_message("✅ Preço atualizado!", ephemeral=True)
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

@bot.tree.command(name="painel", description="Painel de Configuração Geral")
async def painel(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    pix = get_db_val("config", "pix_key") or "NÃO CONFIGURADO"
    color = get_db_val("config", "color") or "#00FF00"
    
    embed = discord.Embed(title=f"💎 Central de Comando - {BOT_NAME}", color=int(color.replace("#",""), 16))
    embed.add_field(name="🔑 Chave PIX", value=f"`{pix}`", inline=True)
    embed.add_field(name="🎨 Cor Embed", value=f"`{color}`", inline=True)
    
    view = discord.ui.View()
    btn_pix = discord.ui.Button(label="Configurar PIX", style=discord.ButtonStyle.primary)
    async def pix_cb(i):
        modal = discord.ui.Modal(title="Configurar PIX")
        input_pix = discord.ui.TextInput(label="Chave PIX")
        async def on_submit(it):
            conn = sqlite3.connect('database.db'); c = conn.cursor()
            c.execute("INSERT OR REPLACE INTO config (key, value) VALUES ('pix_key', ?)", (input_pix.value,))
            conn.commit(); conn.close()
            await it.response.send_message("✅ PIX Atualizado!", ephemeral=True)
        modal.add_item(input_pix); modal.on_submit = on_submit
        await i.response.send_modal(modal)
    btn_pix.callback = pix_cb; view.add_item(btn_pix)
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

@bot.tree.command(name="criar", description="Criar um Produto Profissional")
async def criar(interaction: discord.Interaction):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    modal = discord.ui.Modal(title="Criar Novo Produto")
    id_p = discord.ui.TextInput(label="ID Único (ex: nitro)")
    nome = discord.ui.TextInput(label="Nome do Produto")
    preco = discord.ui.TextInput(label="Preço (ex: 15.00)")
    desc = discord.ui.TextInput(label="Descrição Completa", style=discord.TextStyle.paragraph)
    
    async def on_submit(it):
        conn = sqlite3.connect('database.db'); c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO products (id, name, price, description, stock) VALUES (?, ?, ?, ?, ?)",
                   (id_p.value, nome.value, float(preco.value), desc.value, "[]"))
        conn.commit(); conn.close()
        await it.response.send_message(f"✅ Produto **{nome.value}** criado!", ephemeral=True)
    
    for item in [id_p, nome, preco, desc]: modal.add_item(item)
    modal.on_submit = on_submit; await interaction.response.send_modal(modal)

@bot.tree.command(name="gerenciar", description="Gerenciar um Produto Específico")
async def gerenciar(interaction: discord.Interaction, id_produto: str):
    if interaction.user.id != OWNER_ID: return await interaction.response.send_message("❌", ephemeral=True)
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌ Produto não encontrado.", ephemeral=True)
    
    embed = discord.Embed(title=f"🛠️ Gerenciando: {p[0]}", color=discord.Color.blue())
    embed.add_field(name="💰 Preço Atual", value=f"R$ {p[1]:.2f}")
    embed.add_field(name="📦 Estoque", value=f"{len(json.loads(p[2]))} itens")
    
    await interaction.response.send_message(embed=embed, view=ProductManageView(id_produto), ephemeral=True)

@bot.tree.command(name="vender", description="Enviar Anúncio de Venda")
async def vender(interaction: discord.Interaction, id_produto: str):
    conn = sqlite3.connect('database.db'); c = conn.cursor()
    c.execute("SELECT name, price, description, stock FROM products WHERE id=?", (id_produto,))
    p = c.fetchone(); conn.close()
    if not p: return await interaction.response.send_message("❌ Produto não encontrado.", ephemeral=True)
    
    color = get_db_val("config", "color") or "#00FF00"
    embed = discord.Embed(title=p[0], description=p[2], color=int(color.replace("#",""), 16))
    embed.add_field(name="💰 Valor", value=f"```R$ {p[1]:.2f}```", inline=True)
    embed.add_field(name="📦 Disponível", value=f"```{len(json.loads(p[3]))}```", inline=True)
    embed.set_footer(text=f"© {BOT_NAME} - Compra 100% Segura")
    
    view = discord.ui.View()
    btn_buy = discord.ui.Button(label="Comprar Agora", style=discord.ButtonStyle.success, emoji="🛒")
    
    async def buy_cb(i):
        chave = get_db_val("config", "pix_key")
        if not chave: return await i.response.send_message("❌ PIX não configurado.", ephemeral=True)
        
        # API PIX Profissional
        url = f"https://api.geradornp.com.br/pix/gerar?chave={chave}&valor={p[1]}&nome=LW_ALUGUEL&cidade=BRASIL"
        res = requests.get(url).json()
        
        e = discord.Embed(title="💳 Pagamento Gerado", color=0xFFFF00)
        e.add_field(name="Copia e Cola", value=f"```\n{res['payload']}\n```")
        e.set_image(url=res['qrcode'])
        await i.response.send_message(embed=e, ephemeral=True)
        
    btn_buy.callback = buy_cb; view.add_item(btn_buy)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("✅ Anúncio enviado!", ephemeral=True)

@bot.event
async def on_ready():
    init_db()
    print(f"🚀 {bot.user.name} Online e Robusto!")

bot.run(TOKEN)
