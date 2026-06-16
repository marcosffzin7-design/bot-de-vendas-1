const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionType, AttachmentBuilder, SlashCommandBuilder, REST, Routes } = require('discord.js');
const { JsonDatabase } = require('wio.db');
const express = require('express');
const qrcode = require('qrcode');

// --- BANCO DE DADOS ---
const db = new JsonDatabase({ databasePath: "./database.json" });

// --- CONFIGURAÇÃO (TOKEN FIXO PARA EVITAR ERROS) ---
const config = {
    token: "MTUxNjUzMjg3MjA1MDM3Njg0NA.G0lOd_.fJBN5pZ6WrWnJ6H6tGVmruZ7mPd9Uny2OFAFUw",
    owner_id: "1385438838670889042",
    pix_key: db.get('config.pix') || "NÃO CONFIGURADO",
    bot_name: "LW ALUGUEL",
    color: db.get('config.color') || "#00FF00"
};

// --- WEB SERVER (KEEP ALIVE) ---
const app = express();
app.get('/', (req, res) => res.send('Super Bot LW ALUGUEL Online!'));
app.listen(process.env.PORT || 8080);

// --- CLIENT ---
const client = new Client({ intents: [GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent, GatewayIntentBits.GuildMembers] });

// --- REGISTRO DE COMANDOS ---
const commands = [
    new SlashCommandBuilder().setName('painel').setDescription('Abre o painel principal de gerenciamento'),
    new SlashCommandBuilder().setName('criar').setDescription('Cria um novo produto profissional'),
    new SlashCommandBuilder().setName('vender').setDescription('Envia o anúncio de um produto').addStringOption(o => o.setName('id').setDescription('ID do produto').setRequired(true))
].map(c => c.toJSON());

const rest = new REST({ version: '10' }).setToken(config.token);

client.once('ready', async () => {
    try {
        console.log('🔄 Registrando comandos globais...');
        await rest.put(Routes.applicationCommands(client.user.id), { body: commands });
        console.log(`🚀 ${client.user.tag} ONLINE e Comandos Registrados!`);
    } catch (e) { console.error('Erro ao registrar comandos:', e); }
});

// --- FUNÇÕES AUXILIARES ---
const getProductEmbed = (id) => {
    const p = db.get(`prod_${id}`);
    if (!p) return new EmbedBuilder().setTitle("Erro").setDescription("Produto não encontrado.");
    
    return new EmbedBuilder()
        .setTitle(p.nome)
        .setDescription(p.desc || "Sem descrição.")
        .addFields(
            { name: "💰 Preço", value: `R$ ${p.preco}`, inline: true },
            { name: "📦 Estoque", value: `${p.estoque ? p.estoque.length : 0}`, inline: true }
        )
        .setColor(config.color)
        .setThumbnail(p.thumb || null)
        .setImage(p.banner || null);
};

// --- INTERAÇÕES ---
client.on('interactionCreate', async (interaction) => {
    // 1. SLASH COMMANDS
    if (interaction.isChatInputCommand()) {
        if (interaction.user.id !== config.owner_id) return interaction.reply({ content: "❌ Sem permissão.", ephemeral: true });

        if (interaction.commandName === 'painel') {
            const embed = new EmbedBuilder()
                .setTitle(`💎 Central de Comando - ${config.bot_name}`)
                .setDescription("Gerencie seu bot e visualize estatísticas.")
                .addFields(
                    { name: "🔑 PIX", value: `\`${config.pix_key}\``, inline: true },
                    { name: "📦 Produtos", value: `\`${Object.keys(db.all()).filter(k => k.startsWith('prod_')).length}\``, inline: true }
                ).setColor(config.color);
            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId('conf_pix').setLabel('Configurar PIX').setStyle(ButtonStyle.Primary),
                new ButtonBuilder().setCustomId('conf_visual').setLabel('Personalizar Bot').setStyle(ButtonStyle.Secondary)
            );
            await interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }

        if (interaction.commandName === 'criar') {
            const modal = new ModalBuilder().setCustomId('modal_criar_full').setTitle('Criar Produto Profissional');
            modal.addComponents(
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('id').setLabel('ID Único').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('nome').setLabel('Nome do Produto').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('preco').setLabel('Preço Base').setStyle(TextInputStyle.Short).setRequired(true)),
                new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('desc').setLabel('Descrição Completa').setStyle(TextInputStyle.Paragraph).setRequired(true))
            );
            await interaction.showModal(modal);
        }

        if (interaction.commandName === 'vender') {
            const id = interaction.options.getString('id');
            if (!db.has(`prod_${id}`)) return interaction.reply({ content: "❌ Produto não encontrado.", ephemeral: true });
            
            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`buy_menu_${id}`).setLabel('Comprar Agora').setEmoji('🛒').setStyle(ButtonStyle.Success),
                new ButtonBuilder().setCustomId(`manage_prod_${id}`).setLabel('⚙️ Gerenciar').setStyle(ButtonStyle.Secondary)
            );
            await interaction.channel.send({ embeds: [getProductEmbed(id)], components: [row] });
            await interaction.reply({ content: "✅ Anúncio enviado!", ephemeral: true });
        }
    }

    // 2. BOTÕES
    if (interaction.isButton()) {
        const parts = interaction.customId.split('_');
        const action = parts[0];
        const sub = parts[1];
        const id = parts[2];

        if (action === 'buy') {
            const p = db.get(`prod_${id}`);
            if (!p || p.estoque.length === 0) return interaction.reply({ content: "❌ Estoque esgotado!", ephemeral: true });
            return generatePayment(interaction, id, p.preco, p.nome);
        }

        if (action === 'manage') {
            if (interaction.user.id !== config.owner_id) return interaction.reply({ content: "❌ Sem permissão.", ephemeral: true });
            const p = db.get(`prod_${id}`);
            const embed = new EmbedBuilder().setTitle(`🛠️ Gerenciando: ${p.nome}`).setColor(config.color);
            const row = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`stock_add_${id}`).setLabel('Add Estoque').setStyle(ButtonStyle.Success),
                new ButtonBuilder().setCustomId(`stock_clear_${id}`).setLabel('Limpar Estoque').setStyle(ButtonStyle.Danger)
            );
            await interaction.reply({ embeds: [embed], components: [row], ephemeral: true });
        }

        if (action === 'stock' && sub === 'add') {
            const modal = new ModalBuilder().setCustomId(`modal_stock_add_${id}`).setTitle('Adicionar Itens');
            modal.addComponents(new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('itens').setLabel('Itens (um por linha)').setStyle(TextInputStyle.Paragraph).setRequired(true)));
            await interaction.showModal(modal);
        }

        if (interaction.customId === 'conf_pix') {
            const modal = new ModalBuilder().setCustomId('modal_pix').setTitle('Configurar PIX');
            modal.addComponents(new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('pix').setLabel('Chave PIX').setStyle(TextInputStyle.Short).setRequired(true)));
            await interaction.showModal(modal);
        }
    }

    // 3. MODAIS
    if (interaction.type === InteractionType.ModalSubmit) {
        if (interaction.customId === 'modal_criar_full') {
            const id = interaction.fields.getTextInputValue('id');
            db.set(`prod_${id}`, { 
                id, 
                nome: interaction.fields.getTextInputValue('nome'), 
                preco: interaction.fields.getTextInputValue('preco'), 
                desc: interaction.fields.getTextInputValue('desc'),
                estoque: []
            });
            await interaction.reply({ content: "✅ Produto criado!", ephemeral: true });
        }

        if (interaction.customId === 'modal_pix') {
            const pix = interaction.fields.getTextInputValue('pix');
            db.set('config.pix', pix);
            config.pix_key = pix;
            await interaction.reply({ content: "✅ Chave PIX atualizada!", ephemeral: true });
        }

        if (interaction.customId.startsWith('modal_stock_add_')) {
            const id = interaction.customId.replace('modal_stock_add_', '');
            const itens = interaction.fields.getTextInputValue('itens').split('\n').filter(i => i.trim() !== "");
            const p = db.get(`prod_${id}`);
            p.estoque.push(...itens);
            db.set(`prod_${id}`, p);
            await interaction.reply({ content: `✅ ${itens.length} itens adicionados!`, ephemeral: true });
        }
    }
});

async function generatePayment(interaction, id, preco, nome) {
    if (config.pix_key === "NÃO CONFIGURADO") return interaction.reply({ content: "❌ Configure o PIX no /painel primeiro.", ephemeral: true });
    const pix_code = `00020126360014BR.GOV.BCB.PIX0114${config.pix_key}5204000053039865404${preco}5802BR5908VENDEDOR6008BRASILIA62070503***6304`;
    const qr = await qrcode.toBuffer(pix_code);
    const embed = new EmbedBuilder()
        .setTitle(`Pagamento: ${nome}`)
        .setDescription(`Valor: **R$ ${preco}**\n\nCopie o código abaixo:`)
        .addFields({ name: "Copia e Cola", value: `\`\`\`${pix_code}\`\`\`` })
        .setImage('attachment://qr.png').setColor("#FFFF00");
    await interaction.reply({ embeds: [embed], files: [new AttachmentBuilder(qr, { name: 'qr.png' })], ephemeral: true });
}

client.login(config.token);
