const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionType } = require('discord.js');
const { JsonDatabase } = require('wio.db');
const express = require('express');
const qrcode = require('qrcode');
const axios = require('axios');
const path = require('path');

// --- BANCO DE DADOS ---
const db = new JsonDatabase({ databasePath: "./database.json" });

// --- CONFIGURAÇÃO ---
const config = {
    token: process.env.TOKEN || "MTUxNjUzMjg3MjA1MDM3Njg0NA.GsQ_i-.TXZE3EOm5Kz_6BmL3lfskmTDZRHQsBJ3XuMyeQ",
    pix_key: process.env.PIX_KEY || "SUA_CHAVE_PIX",
    owner_id: process.env.OWNER_ID || "1385438838670889042",
    color: "#00FF00"
};

// --- WEB SERVER (KEEP ALIVE) ---
const app = express();
app.get('/', (req, res) => res.send('Bot de Vendas Online!'));
app.listen(process.env.PORT || 8080);

// --- CLIENT DISCORD ---
const client = new Client({
    intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent]
});

client.once('ready', () => {
    console.log(`✅ Logado como ${client.user.tag}`);
});

// --- COMANDOS ---
client.on('messageCreate', async (message) => {
    if (message.author.bot || !message.content.startsWith('!')) return;

    const args = message.content.slice(1).trim().split(/ +/);
    const command = args.shift().toLowerCase();

    // 1. SETUP PIX
    if (command === 'setup_pix' && message.author.id === config.owner_id) {
        const modal = new ModalBuilder()
            .setCustomId('modal_setup_pix')
            .setTitle('Configurar PIX');

        const input = new TextInputBuilder()
            .setCustomId('pix_key')
            .setLabel('Sua Chave PIX')
            .setStyle(TextInputStyle.Short)
            .setRequired(true);

        modal.addComponents(new ActionRowBuilder().addComponents(input));
        // Nota: Modais só funcionam via Interaction. Para comando de texto, usamos um botão.
        const row = new ActionRowBuilder().addComponents(
            new ButtonBuilder().setCustomId('btn_open_setup').setLabel('Abrir Configuração').setStyle(ButtonStyle.Primary)
        );
        return message.reply({ content: 'Clique abaixo para configurar:', components: [row] });
    }

    // 2. CRIAR PRODUTO
    if (command === 'criar' && message.author.id === config.owner_id) {
        const [id, preco, ...nomeArray] = args;
        const nome = nomeArray.join(' ');

        if (!id || !preco || !nome) return message.reply('Uso: `!criar [id] [preço] [nome]`');

        db.set(`prod_${id}`, { id, preco, nome, estoque: [] });
        
        const embed = new EmbedBuilder()
            .setTitle(nome)
            .setDescription(`💰 Preço: R$ ${preco}\n📦 Estoque: 0`)
            .setColor(config.color);

        const row = new ActionRowBuilder().addComponents(
            new ButtonBuilder().setCustomId(`buy_${id}`).setLabel('Comprar').setStyle(ButtonStyle.Success)
        );

        message.channel.send({ embeds: [embed], components: [row] });
    }

    // 3. ADICIONAR ESTOQUE
    if (command === 'add' && message.author.id === config.owner_id) {
        const [id, ...conteudo] = args;
        if (!id || conteudo.length === 0) return message.reply('Uso: `!add [id] [conteúdo]`');

        if (!db.has(`prod_${id}`)) return message.reply('Produto não encontrado!');

        db.push(`prod_${id}.estoque`, conteudo.join(' '));
        message.reply(`✅ Item adicionado ao estoque de \`${id}\`!`);
    }
});

// --- INTERAÇÕES (BOTÕES E MODAIS) ---
client.on('interactionCreate', async (interaction) => {
    if (interaction.isButton()) {
        if (interaction.customId === 'btn_open_setup') {
            const modal = new ModalBuilder().setCustomId('modal_setup_pix').setTitle('Configurar PIX');
            const input = new TextInputBuilder().setCustomId('pix_key').setLabel('Sua Chave PIX').setStyle(TextInputStyle.Short).setRequired(true);
            modal.addComponents(new ActionRowBuilder().addComponents(input));
            return await interaction.showModal(modal);
        }

        if (interaction.customId.startsWith('buy_')) {
            const id = interaction.customId.replace('buy_', '');
            const prod = db.get(`prod_${id}`);

            if (prod.estoque.length === 0) return interaction.reply({ content: '❌ Estoque esgotado!', ephemeral: true });

            // Simulação de geração de PIX (Copia e Cola estático para simplicidade)
            // Em um sistema real, você usaria uma API de pagamento.
            const pix_msg = `00020126360014BR.GOV.BCB.PIX0114${config.pix_key}5204000053039865404${prod.preco}5802BR5908VENDEDOR6008BRASILIA62070503***6304`;
            
            const embed = new EmbedBuilder()
                .setTitle('Pagamento PIX')
                .setDescription(`Você está comprando: **${prod.nome}**\nValor: **R$ ${prod.preco}**\n\nCopie o código abaixo para pagar:`)
                .addFields({ name: 'Copia e Cola', value: `\`\`\`${pix_msg}\`\`\`` })
                .setColor('#FFFF00');

            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`confirm_${id}`).setLabel('Já Paguei').setStyle(ButtonStyle.Primary)
            );

            await interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }

        if (interaction.customId.startsWith('confirm_')) {
            await interaction.reply({ content: '📩 Envie o comprovante para um administrador aprovar.', ephemeral: true });
        }
    }

    if (interaction.type === InteractionType.ModalSubmit) {
        if (interaction.customId === 'modal_setup_pix') {
            const novaChave = interaction.fields.getTextInputValue('pix_key');
            config.pix_key = novaChave;
            await interaction.reply({ content: `✅ Chave PIX atualizada para: \`${novaChave}\``, ephemeral: true });
        }
    }
});

client.login(config.token);
