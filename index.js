const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionType, AttachmentBuilder, SlashCommandBuilder, REST, Routes } = require('discord.js');
const { JsonDatabase } = require('wio.db');
const express = require('express');
const qrcode = require('qrcode');

// --- BANCO DE DADOS ---
const db = new JsonDatabase({ databasePath: "./database.json" });

// --- CONFIGURAÇÃO ---
const config = {
    token: process.env.TOKEN || "MTUxNjUzMjg3MjA1MDM3Njg0NA.G0lOd_.fJBN5pZ6WrWnJ6H6tGVmruZ7mPd9Uny2OFAFUw",
    client_id: process.env.CLIENT_ID || "1516532872050376844",
    owner_id: process.env.OWNER_ID || "1385438838670889042",
    pix_key: db.get('config.pix') || "NÃO CONFIGURADO",
    bot_name: db.get('config.name') || "SZZ VENDAS PRO",
    color: db.get('config.color') || "#00FF00"
};

// --- WEB SERVER ---
const app = express();
app.get('/', (req, res) => res.send('Bot Online!'));
app.listen(process.env.PORT || 8080);

// --- CLIENT ---
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent] });

// --- REGISTRO DE SLASH COMMANDS ---
const commands = [
    new SlashCommandBuilder().setName('config').setDescription('Painel de configuração geral do bot'),
    new SlashCommandBuilder().setName('criar').setDescription('Criar um novo produto'),
    new SlashCommandBuilder().setName('gerenciar').setDescription('Abrir painel de gerenciamento de um produto').addStringOption(opt => opt.setName('id').setDescription('ID do produto').setRequired(true)),
    new SlashCommandBuilder().setName('vender').setDescription('Enviar anúncio de venda de um produto').addStringOption(opt => opt.setName('id').setDescription('ID do produto').setRequired(true))
].map(command => command.toJSON());

const rest = new REST({ version: '10' }).setToken(config.token);

(async () => {
    try {
        console.log('🔄 Registrando comandos (/)...');
        await rest.put(Routes.applicationCommands(config.client_id), { body: commands });
        console.log('✅ Comandos registrados!');
    } catch (error) { console.error(error); }
})();

client.once('ready', () => console.log(`🚀 ${client.user.tag} está online!`));

// --- INTERAÇÕES ---
client.on('interactionCreate', async (interaction) => {
    // 1. SLASH COMMANDS
    if (interaction.isChatInputCommand()) {
        if (interaction.user.id !== config.owner_id) return interaction.reply({ content: "❌ Apenas o dono pode usar este comando.", ephemeral: true });

        if (interaction.commandName === 'config') {
            const embed = new EmbedBuilder()
                .setTitle(`⚙️ Configurações - ${config.bot_name}`)
                .addFields(
                    { name: "🔑 Chave PIX", value: `\`${config.pix_key}\``, inline: true },
                    { name: "🎨 Cor", value: `\`${config.color}\``, inline: true }
                )
                .setColor(config.color);
            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId('edit_pix').setLabel('Editar PIX').setStyle(ButtonStyle.Primary),
                new ButtonBuilder().setCustomId('edit_visual').setLabel('Editar Nome/Cor').setStyle(ButtonStyle.Secondary)
            );
            await interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }

        if (interaction.commandName === 'criar') {
            const modal = new ModalBuilder().setCustomId('modal_criar').setTitle('Novo Produto');
            modal.addComponents(
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('id').setLabel('ID do Produto').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('nome').setLabel('Nome').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('preco').setLabel('Preço').setStyle(TextInputStyle.Short).setRequired(true))
            );
            await interaction.showModal(modal);
        }

        if (interaction.commandName === 'gerenciar') {
            const id = interaction.options.getString('id');
            const prod = db.get(`prod_${id}`);
            if (!prod) return interaction.reply({ content: "❌ Produto não encontrado!", ephemeral: true });

            const embed = new EmbedBuilder()
                .setTitle(`🛠️ Gerenciar: ${prod.nome}`)
                .setDescription(`ID: \`${id}\` | Preço: \`R$ ${prod.preco}\` | Estoque: \`${prod.estoque.length}\``)
                .setColor(config.color);

            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`add_stock_${id}`).setLabel('Add Estoque').setStyle(ButtonStyle.Success),
                new ButtonBuilder().setCustomId(`clear_stock_${id}`).setLabel('Limpar Estoque').setStyle(ButtonStyle.Danger),
                new ButtonBuilder().setCustomId(`edit_prod_${id}`).setLabel('Editar Info').setStyle(ButtonStyle.Secondary)
            );
            await interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }

        if (interaction.commandName === 'vender') {
            const id = interaction.options.getString('id');
            const prod = db.get(`prod_${id}`);
            if (!prod) return interaction.reply({ content: "❌ Produto não encontrado!", ephemeral: true });

            const embed = new EmbedBuilder()
                .setTitle(prod.nome)
                .setDescription("Selecione uma opção abaixo para comprar.")
                .addFields({ name: "💰 Preço", value: `R$ ${prod.preco}`, inline: true }, { name: "📦 Estoque", value: `${prod.estoque.length}`, inline: true })
                .setColor(config.color);

            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`buy_${id}`).setLabel('Comprar').setEmoji('🛒').setStyle(ButtonStyle.Success)
            );
            await interaction.reply({ content: "✅ Anúncio enviado!", ephemeral: true });
            await interaction.channel.send({ embeds: [embed], components: [row] });
        }
    }

    // 2. BOTÕES E MODAIS (Lógica de Venda e Gestão)
    if (interaction.isButton()) {
        const [action, subAction, id] = interaction.customId.split('_');

        if (action === 'buy') {
            const prod = db.get(`prod_${id}`);
            if (prod.estoque.length === 0) return interaction.reply({ content: "❌ Estoque esgotado!", ephemeral: true });

            const pix_code = `00020126360014BR.GOV.BCB.PIX0114${config.pix_key}5204000053039865404${prod.preco}5802BR5908VENDEDOR6008BRASILIA62070503***6304`;
            const qrBuffer = await qrcode.toBuffer(pix_code);
            const attachment = new AttachmentBuilder(qrBuffer, { name: 'qrcode.png' });

            const embed = new EmbedBuilder()
                .setTitle(`Pagamento - ${prod.nome}`)
                .addFields({ name: "Valor", value: `R$ ${prod.preco}` }, { name: "Copia e Cola", value: `\`\`\`${pix_code}\`\`\`` })
                .setImage('attachment://qrcode.png').setColor("#FFFF00");

            await interaction.reply({ embeds: [embed], files: [attachment], ephemeral: true });
        }

        if (action === 'add' && subAction === 'stock') {
            const modal = new ModalBuilder().setCustomId(`modal_add_stock_${id}`).setTitle('Adicionar ao Estoque');
            modal.addComponents(new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('itens').setLabel('Itens (um por linha)').setStyle(TextInputStyle.Paragraph).setRequired(true)));
            await interaction.showModal(modal);
        }
    }

    if (interaction.type === InteractionType.ModalSubmit) {
        if (interaction.customId === 'modal_criar') {
            const id = interaction.fields.getTextInputValue('id');
            const nome = interaction.fields.getTextInputValue('nome');
            const preco = interaction.fields.getTextInputValue('preco');
            db.set(`prod_${id}`, { id, nome, preco, estoque: [] });
            await interaction.reply({ content: `✅ Produto **${nome}** criado!`, ephemeral: true });
        }

        if (interaction.customId.startsWith('modal_add_stock_')) {
            const id = interaction.customId.replace('modal_add_stock_', '');
            const itens = interaction.fields.getTextInputValue('itens').split('\n');
            const prod = db.get(`prod_${id}`);
            prod.estoque.push(...itens);
            db.set(`prod_${id}`, prod);
            await interaction.reply({ content: `✅ ${itens.length} itens adicionados ao estoque de **${prod.nome}**!`, ephemeral: true });
        }
    }
});

client.login(config.token);
