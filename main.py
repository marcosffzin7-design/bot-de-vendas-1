import discord
from discord.ext import commands
import os
import sqlite3
import qrcode
from io import BytesIO
from flask import Flask
from threading import Thread

# --- TRATAMENTO DO TOKEN ---
# O strip() remove espaços invisíveis que causam o erro 401
raw_token = os.getenv("TOKEN", "")
TOKEN = raw_token.strip()

print("--- DEBUG DE INICIALIZAÇÃO ---")
if not TOKEN:
    print("❌ ERRO: NENHUM TOKEN ENCONTRADO!")
    print("Certifique-se de que a variável 'TOKEN' existe no Render -> Environment.")
else:
    print(f"✅ Token carregado. Tamanho: {len(TOKEN)} caracteres.")
    if len(TOKEN) < 50:
        print("⚠️ AVISO: Seu token parece curto demais. Verifique se copiou ele todo.")
print("------------------------------")

# --- BANCO DE DADOS ---
def init_db():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS products 
                      (id TEXT PRIMARY KEY, name TEXT, price REAL, description TEXT, stock TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS config 
                      (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    conn.close()

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "Bot Online!"

def run_web():
    app.run(host='0.0.0.0', port=int(os.getenv("PORT", 8080)))

Thread(target=run_web, daemon=True).start()

# --- BOT ---
class LWBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.all()
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        print("🔄 Sincronizando comandos...")
        await self.tree.sync()

bot = LWBot()

@bot.event
async def on_ready():
    init_db()
    print(f"🚀 SUCESSO! {bot.user.name} está online.")

if __name__ == "__main__":
    try:
        if TOKEN:
            bot.run(TOKEN)
        else:
            print("❌ Falha ao iniciar: Token vazio.")
    except discord.errors.LoginFailure:
        print("❌ ERRO 401: O Discord recusou o token.")
        print("SOLUÇÃO: Vá no Developer Portal, clique em 'Reset Token' e coloque o novo no Render.")
    except Exception as e:
        print(f"❌ Erro inesperado: {e}")
