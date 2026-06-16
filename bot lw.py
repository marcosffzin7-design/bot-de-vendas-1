import discord
import aiohttp
import json
import os
import qrcode
import uuid
import base64
from discord.ext import commands
from discord.ui import Button, View
from io import BytesIO
from flask import Flask
from threading import Thread
from brcode.payments import Payment
from brcode.data import StaticPixData

# --- CONFIGURAÇÃO E DADOS ---
CONFIG_FILE = "config.json"
PRODUCTS_FILE = "products.json"

DEFAULT_CONFIG = {
    "TOKEN": "SEU_TOKEN_AQUI",
    "PREFIX": "!",
    "BOT_NAME": "LW ALUGUEL",
    "EMBED_COLOR": "#00ff00",
    "PIX_KEY": "SUA_CHAVE_PIX_AQUI"
}

def load_json(filename, default):
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(filename, data):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

config = load_json(CONFIG_FILE, DEFAULT_CONFIG)
products = load_json(PRODUCTS_FILE, [])

# --- SERVIDOR KEEP-ALIVE (FLASK) ---
app = Flask('')
@app.route('/')
def home(): return "Bot LW ALUGUEL Online!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    Thread(target=run_flask).start()

# --- BOT DISCORD ---
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix=config["PREFIX"], intents=intents)
bot.pending_confirmations = {}

@bot.event
async def on_ready():
    print(f"✅ {bot.user.name} está online!")

# --- INTERFACE (BOTÕES) ---
class AdminApprovalView(View):
    def __init__(self, request_id):
        super().__init__(timeout=None)
        self.request_id = request_id

    @discord.ui.button(label="Aprovar ✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Apenas ADMs!", ephemeral=True)
        
        if self.request_id in bot.pending_confirmations:
            data = bot.pending_confirmations[self.request_id]
            user = await bot.fetch_user(data["user_id"])
            
            delivery = "Obrigado!"
            for p in products:
                if p["id"] == data["product_id"]:
                    for plan in p["plans"]:
                        if plan["name"].lower() == data["plan_name"].lower():
                            delivery = plan.get("delivery_content", delivery)
            
            if user:
                embed = discord.Embed(title="Pagamento Aprovado! 🎉", color=discord.Color.green())
                embed.add_field(name="Entrega", value=f"```\n{delivery}\n```")
                try: await user.send(embed=embed)
                except: pass
            
            del bot.pending_confirmations[self.request_id]
            await interaction.response.send_message("Aprovado e entregue!")
            self.stop()

    @discord.ui.button(label="Recusar ❌", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator: return
        if self.request_id in bot.pending_confirmations:
            del bot.pending_confirmations[self.request_id]
            await interaction.response.send_message("Recusado.")
            self.stop()

class ConfirmPaymentView(View):
    def __init__(self, product_id, plan_name):
        super().__init__(timeout=None)
        self.product_id = product_id
        self.plan_name = plan_name

    @discord.ui.button(label="Já Paguei (Enviar Comprovante)", style=discord.ButtonStyle.primary)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Envie o **print do comprovante** agora.", ephemeral=True)
        def check(m): return m.author == interaction.user and m.attachments
        try:
            msg = await bot.wait_for('message', check=check, timeout=300)
            req_id = str(uuid.uuid4())[:8]
            bot.pending_confirmations[req_id] = {"user_id": interaction.user.id, "product_id": self.product_id, "plan_name": self.plan_name}
            
            adm_embed = discord.Embed(title="🔔 Novo Comprovante", color=discord.Color.gold())
            adm_embed.add_field(name="Cliente", value=f"<@{interaction.user.id}>")
            adm_embed.add_field(name="Item", value=f"{self.product_id} - {self.plan_name}")
            adm_embed.set_image(url=msg.attachments[0].url)
            
            await interaction.channel.send(embed=adm_embed, view=AdminApprovalView(req_id))
            await interaction.followup.send("Enviado! Aguarde a aprovação.", ephemeral=True)
        except: await interaction.followup.send("Erro ou tempo esgotado.", ephemeral=True)

# --- COMANDOS ---
@bot.command()
async def listproducts(ctx):
    if not products: return await ctx.send("Sem produtos.")
    embed = discord.Embed(title=config["BOT_NAME"], color=discord.Color.from_str(config["EMBED_COLOR"]))
    for p in products:
        plans = "\n".join([f"🔹 {plan['name']}: R$ {plan['price']:.2f}" for plan in p['plans']])
        embed.add_field(name=f"📦 {p['name']} (ID: {p['id']})", value=f"{p['description']}\n\n{plans}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
async def pay(ctx, product_id, plan_name):
    product = next((p for p in products if p["id"] == product_id), None)
    plan = next((pl for pl in product["plans"] if pl["name"].lower() == plan_name.lower()), None) if product else None
    if not product or not plan: return await ctx.send("Não encontrado.")
    
    pix = StaticPixData(key=config["PIX_KEY"], merchant_name=config["BOT_NAME"], merchant_city="BRASIL", amount=plan["price"])
    brcode = Payment(pix).to_brcode()
    
    qr = qrcode.QRCode(box_size=10, border=4)
    qr.add_data(brcode); qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO(); img.save(buf, format="PNG"); buf.seek(0)
    
    embed = discord.Embed(title="Pagamento PIX", description=f"**{product['name']}** - {plan['name']}\nValor: R$ {plan['price']:.2f}", color=discord.Color.from_str(config["EMBED_COLOR"]))
    embed.add_field(name="Copia e Cola", value=f"```\n{brcode}\n```")
    embed.set_image(url="attachment://qr.png")
    await ctx.send(file=discord.File(buf, "qr.png"), embed=embed, view=ConfirmPaymentView(product_id, plan_name))

@bot.command()
@commands.has_permissions(administrator=True)
async def setpix(ctx, *, key):
    config["PIX_KEY"] = key; save_json(CONFIG_FILE, config)
    await ctx.send("Chave PIX atualizada!")

@bot.command()
@commands.has_permissions(administrator=True)
async def addproduct(ctx, id, name, desc):
    products.append({"id": id, "name": name, "description": desc, "plans": []})
    save_json(PRODUCTS_FILE, products); await ctx.send("Produto adicionado!")

@bot.command()
@commands.has_permissions(administrator=True)
async def addplan(ctx, prod_id, name, price: float, *, delivery):
    for p in products:
        if p["id"] == prod_id:
            p["plans"].append({"name": name, "price": price, "delivery_content": delivery})
            save_json(PRODUCTS_FILE, products); return await ctx.send("Plano adicionado!")
    await ctx.send("Produto não encontrado.")

if __name__ == "__main__":
    keep_alive()
    bot.run(config["TOKEN"])
