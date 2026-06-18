"""
🛍️ BOT DE VENDAS DISCORD - CÓDIGO COMPLETO STANDALONE
======================================================

Um bot simples e completo para gerenciar vendas no Discord.
Inclui: catálogo, carrinho, checkout e controle de estoque.

ARQUIVO ÚNICO - SEM DEPENDÊNCIAS EXTERNAS!

Para usar:
1. Instale discord.py: pip install discord.py
2. Edite a linha com TOKEN = "seu_token_aqui" (linha ~35)
3. Execute: python bot_completo_standalone.py

Comandos:
- /catalogo: Visualiza produtos
- /carrinho: Mostra seu carrinho
"""

import os
import json
import discord
from discord.ext import commands
from discord import app_commands

# ============================================================================
# CONFIGURAÇÃO - EDITE AQUI COM SEU TOKEN
# ============================================================================

TOKEN = "MTUxNjUzMjg3MjA1MDM3Njg0NA.Gb1igg.4sRN_CE6N970Jbel-WwZ3ZJUt8FKto82GOoel8"  # ← COLOQUE SEU TOKEN AQUI!

# Se preferir usar variável de ambiente, descomente a linha abaixo:
# TOKEN = os.getenv('TOKEN', 'MTUxNjUzMjg3MjA1MDM3Njg0NA.Gb1igg.4sRN_CE6N970Jbel-WwZ3ZJUt8FKto82GOoel8')

# ============================================================================
# CONFIGURAÇÃO DO BOT
# ============================================================================

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Nomes dos arquivos de banco de dados
PRODUCTS_FILE = 'produtos.json'
CARTS_FILE = 'carrinhos.json'

# Produtos padrão (criados na primeira execução)
PRODUTOS_PADRAO = {
    "produtos": [
        {
            "id": 1,
            "nome": "Produto 1",
            "descricao": "Descrição do produto 1",
            "preco": 29.99,
            "estoque": 10
        },
        {
            "id": 2,
            "nome": "Produto 2",
            "descricao": "Descrição do produto 2",
            "preco": 49.99,
            "estoque": 5
        },
        {
            "id": 3,
            "nome": "Produto 3",
            "descricao": "Descrição do produto 3",
            "preco": 99.99,
            "estoque": 3
        }
    ]
}

# ============================================================================
# FUNÇÕES DE BANCO DE DADOS
# ============================================================================

def carregar_produtos():
    """Carrega produtos do arquivo JSON ou cria com dados padrão"""
    if not os.path.exists(PRODUCTS_FILE):
        with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(PRODUTOS_PADRAO, f, indent=2, ensure_ascii=False)
    with open(PRODUCTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvar_produtos(dados):
    """Salva produtos no arquivo JSON"""
    with open(PRODUCTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

def carregar_carrinhos():
    """Carrega carrinhos do arquivo JSON ou cria vazio"""
    if not os.path.exists(CARTS_FILE):
        with open(CARTS_FILE, 'w', encoding='utf-8') as f:
            json.dump({"carrinhos": {}}, f, indent=2, ensure_ascii=False)
    with open(CARTS_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def salvar_carrinhos(dados):
    """Salva carrinhos no arquivo JSON"""
    with open(CARTS_FILE, 'w', encoding='utf-8') as f:
        json.dump(dados, f, indent=2, ensure_ascii=False)

# ============================================================================
# EVENTOS DO BOT
# ============================================================================

@bot.event
async def on_ready():
    """Executado quando o bot se conecta ao Discord"""
    print(f'✅ Bot conectado como {bot.user}')
    try:
        synced = await bot.tree.sync()
        print(f'✅ {len(synced)} comando(s) sincronizado(s)')
    except Exception as e:
        print(f'❌ Erro ao sincronizar: {e}')

# ============================================================================
# COMANDO: /catalogo
# ============================================================================

@bot.tree.command(name="catalogo", description="Visualize o catálogo de produtos")
async def catalogo(interaction: discord.Interaction):
    """Mostra todos os produtos disponíveis com botões para adicionar ao carrinho"""
    
    produtos = carregar_produtos()['produtos']
    
    if not produtos:
        await interaction.response.send_message("❌ Nenhum produto disponível!", ephemeral=True)
        return
    
    # Criar embed com lista de produtos
    embed = discord.Embed(
        title="🛍️ Catálogo de Produtos",
        description="Clique em um botão para adicionar ao carrinho",
        color=discord.Color.blue()
    )
    
    for produto in produtos:
        embed.add_field(
            name=f"{produto['nome']} - R$ {produto['preco']:.2f}",
            value=f"{produto['descricao']}\n📦 Em estoque: {produto['estoque']}",
            inline=False
        )
    
    # Criar botões para cada produto
    class ProdutoButtons(discord.ui.View):
        def __init__(self):
            super().__init__()
            for produto in produtos:
                if produto['estoque'] > 0:
                    self.add_item(discord.ui.Button(
                        label=f"Adicionar {produto['nome']}",
                        custom_id=f"add_{produto['id']}",
                        style=discord.ButtonStyle.primary
                    ))
        
        async def interaction_callback(self, interaction: discord.Interaction):
            """Executado quando um botão é clicado"""
            produto_id = int(interaction.data['custom_id'].split('_')[1])
            user_id = str(interaction.user.id)
            
            # Carregar dados
            produtos = carregar_produtos()['produtos']
            carrinhos = carregar_carrinhos()
            
            # Encontrar produto
            produto = next((p for p in produtos if p['id'] == produto_id), None)
            
            if not produto:
                await interaction.response.send_message("❌ Produto não encontrado!", ephemeral=True)
                return
            
            # Criar carrinho do usuário se não existir
            if user_id not in carrinhos['carrinhos']:
                carrinhos['carrinhos'][user_id] = []
            
            # Verificar se produto já está no carrinho
            item_existente = next((item for item in carrinhos['carrinhos'][user_id] if item['id'] == produto_id), None)
            
            if item_existente:
                item_existente['quantidade'] += 1
            else:
                carrinhos['carrinhos'][user_id].append({'id': produto_id, 'quantidade': 1})
            
            # Salvar carrinho
            salvar_carrinhos(carrinhos)
            
            await interaction.response.send_message(
                f"✅ **{produto['nome']}** adicionado ao carrinho!",
                ephemeral=True
            )
    
    view = ProdutoButtons()
    await interaction.response.send_message(embed=embed, view=view)

# ============================================================================
# COMANDO: /carrinho
# ============================================================================

@bot.tree.command(name="carrinho", description="Visualize seu carrinho de compras")
async def carrinho(interaction: discord.Interaction):
    """Mostra o carrinho do usuário com opções de checkout"""
    
    user_id = str(interaction.user.id)
    carrinhos = carregar_carrinhos()
    produtos = carregar_produtos()['produtos']
    
    carrinho_usuario = carrinhos['carrinhos'].get(user_id, [])
    
    if not carrinho_usuario:
        await interaction.response.send_message(
            "🛒 Seu carrinho está vazio! Use `/catalogo` para adicionar produtos.",
            ephemeral=True
        )
        return
    
    # Calcular total e criar descrição
    total = 0
    descricao = ""
    
    for idx, item in enumerate(carrinho_usuario, 1):
        produto = next((p for p in produtos if p['id'] == item['id']), None)
        if produto:
            subtotal = produto['preco'] * item['quantidade']
            total += subtotal
            descricao += f"{idx}. **{produto['nome']}** x{item['quantidade']} - R$ {subtotal:.2f}\n"
    
    # Criar embed do carrinho
    embed = discord.Embed(
        title="🛒 Seu Carrinho",
        description=descricao,
        color=discord.Color.green()
    )
    embed.add_field(name="Total", value=f"R$ {total:.2f}", inline=False)
    
    # Criar botões de ação
    class CarrinhoButtons(discord.ui.View):
        @discord.ui.button(label="Finalizar Compra", style=discord.ButtonStyle.success, custom_id="checkout")
        async def checkout(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Finaliza a compra e atualiza estoque"""
            user_id = str(interaction.user.id)
            carrinhos = carregar_carrinhos()
            produtos = carregar_produtos()['produtos']
            
            carrinho_usuario = carrinhos['carrinhos'].get(user_id, [])
            total = 0
            
            # Processar itens do carrinho
            for item in carrinho_usuario:
                produto = next((p for p in produtos if p['id'] == item['id']), None)
                if produto:
                    total += produto['preco'] * item['quantidade']
                    produto['estoque'] -= item['quantidade']
            
            # Salvar mudanças
            salvar_produtos({"produtos": produtos})
            carrinhos['carrinhos'][user_id] = []
            salvar_carrinhos(carrinhos)
            
            # Mensagem de sucesso
            embed_sucesso = discord.Embed(
                title="✅ Compra Realizada!",
                description=f"Obrigado pela compra!\n\n**Total: R$ {total:.2f}**",
                color=discord.Color.green()
            )
            
            await interaction.response.send_message(embed=embed_sucesso, ephemeral=True)
        
        @discord.ui.button(label="Limpar Carrinho", style=discord.ButtonStyle.danger, custom_id="limpar")
        async def limpar(self, interaction: discord.Interaction, button: discord.ui.Button):
            """Limpa o carrinho do usuário"""
            user_id = str(interaction.user.id)
            carrinhos = carregar_carrinhos()
            carrinhos['carrinhos'][user_id] = []
            salvar_carrinhos(carrinhos)
            
            await interaction.response.send_message("🗑️ Carrinho limpo com sucesso!", ephemeral=True)
    
    await interaction.response.send_message(embed=embed, view=CarrinhoButtons(), ephemeral=True)

# ============================================================================
# INICIAR BOT
# ============================================================================

if __name__ == "__main__":
    if not TOKEN or TOKEN == "seu_token_do_bot_aqui":
        print("❌ ERRO: TOKEN não configurado!")
        print("Edite a linha 35 do arquivo e adicione seu token do Discord")
        print("Obtenha seu token em: https://discord.com/developers/applications")
        exit(1)
    
    print("🚀 Iniciando bot...")
    print(f"Token: {TOKEN[:10]}..." if len(TOKEN) > 10 else "Token configurado")
    bot.run(TOKEN)
