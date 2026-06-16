const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionType, AttachmentBuilder, SlashCommandBuilder, REST, Routes } = require('discord.js');
const { JsonDatabase } = require('wio.db');
const express = require('express');
const qrcode = require('qrcode');

// --- BANCO DE DADOS ---
const db = new JsonDatabase({ databasePath: "./database.json" });

// --- CONFIGURAÇÃO FIXA ---
const config = {
    token: "MTUxNjUzMjg3MjA1MDM3Njg0NA.G0lOd_.fJBN5pZ6WrWnJ6H6tGVmruZ7mPd9Uny2OFAFUw",
    client_id: "1516532872050376844",
    owner_id: "1385438838670889042",
    guild_id: "1516543103387828286",
    pix_key: db.get('config.pix') || "NÃO CONFIGURADO",
    bot_name: "LW ALUGUEL",
    color: db.get('config.color') || "#00FF00"
};

// --- WEB SERVER (KEEP ALIVE) ---
const app = express();
app.get('/', (req, res) => res.send('Bot LW ALUGUEL Online!'));
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
        console.log('🔄 Registrando comandos (/) no servidor...');
        await rest.put(Routes.applicationGuildCommands(config.client_id, config.guild_id), { body: commands });
        console.log('✅ Comandos registrados com sucesso!');
    } catch (error) { console.error('❌ Erro ao registrar comandos:', error); }
})();

client.once('ready', () => {
    console.log(`🚀 ${client.user.tag} está online e pronto para vender!`);
});

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
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('id').setLabel('ID do Produto (ex: nitro)').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('nome').setLabel('Nome').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('preco').setLabel('Preço (ex: 10.00)').setStyle(TextInputStyle.Short).setRequired(true))
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
                new ButtonBuilder().setCustomId(`clear_stock_${id}`).setLabel('Limpar Estoque').setStyle(ButtonStyle.Danger)
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

    // 2. BOTÕES E MODAIS
    if (interaction.isButton()) {
        const parts = interaction.customId.split('_');
        const action = parts[0];
        const subAction = parts[1];
        const id = parts[2];

        if (action === 'buy') {
            const prod = db.get(`prod_${id}`);
            if (!prod || prod.estoque.length === 0) return interaction.reply({ content: "❌ Estoque esgotado!", ephemeral: true });

            if (config.pix_key === "NÃO CONFIGURADO") return interaction.reply({ content: "❌ O dono ainda não configurou a chave PIX!", ephemeral: true });

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

        if (interaction.customId === 'edit_pix') {
            const modal = new ModalBuilder().setCustomId('modal_conf_pix').setTitle('Configurar PIX');
            modal.addComponents(new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('pix').setLabel('Chave PIX').setStyle(TextInputStyle.Short).setRequired(true)));
            await interaction.showModal(modal);
        }
    }

    if (interaction.type === InteractionType.ModalSubmit) {
        if (interaction.customId === 'modal_criar') {
            const id = interaction.fields.getTextInputValue('id');
            const nome = interaction.fields.getTextInputValue('nome');
            const preco = interaction.fields.getTextInputValue('preco');
            db.set(`prod_${id}`, { id, nome, preco, estoque: [] });
            await interaction.reply({ content: `✅ Produto **${nome}** criado! Use \`/vender ${id}\` para anunciar.`, ephemeral: true });
        }

        if (interaction.customId.startsWith('modal_add_stock_')) {
            const id = interaction.customId.replace('modal_add_stock_', '');
            const itens = interaction.fields.getTextInputValue('itens').split('\n').filter(i => i.trim() !== "");
            const prod = db.get(`prod_${id}`);
            prod.estoque.push(...itens);
            db.set(`prod_${id}`, prod);
            await interaction.reply({ content: `✅ ${itens.length} itens adicionados ao estoque de **${prod.nome}**!`, ephemeral: true });
        }

        if (interaction.customId === 'modal_conf_pix') {
            const novaPix = interaction.fields.getTextInputValue('pix');
            db.set('config.pix', novaPix);
            config.pix_key = novaPix;
            await interaction.reply({ content: "✅ Chave PIX atualizada!", ephemeral: true });
        }
    }
});

client.login(config.token);
