const { Client, GatewayIntentBits, EmbedBuilder, ActionRowBuilder, ButtonBuilder, ButtonStyle, ModalBuilder, TextInputBuilder, TextInputStyle, InteractionType, AttachmentBuilder, SlashCommandBuilder, REST, Routes } = require('discord.js');
const { JsonDatabase } = require('wio.db');
const express = require('express');
const qrcode = require('qrcode');

// --- BANCO DE DADOS ---
const db = new JsonDatabase({ databasePath: "./database.json" });

// --- CONFIGURAÇÃO ---
const config = {
    token: process.env.TOKEN || "SEU_TOKEN_AQUI",
    client_id: "1516532872050376844",
    owner_id: "1385438838670889042",
    guild_id: "1516543103387828286",
    pix_key: db.get('config.pix') || "NÃO CONFIGURADO",
    bot_name: "LW ALUGUEL",
    color: db.get('config.color') || "#00FF00",
    log_channel: db.get('config.log_channel') || null
};

// --- WEB SERVER ---
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
(async () => {
    try {
        await rest.put(Routes.applicationGuildCommands(config.client_id, config.guild_id), { body: commands });
        console.log('✅ Comandos de Elite Registrados!');
    } catch (e) { console.error(e); }
})();

client.once('ready', () => console.log(`🚀 ${client.user.tag} ONLINE!`));

// --- FUNÇÕES AUXILIARES ---
const getProductEmbed = (id) => {
    const p = db.get(`prod_${id}`);
    const embed = new EmbedBuilder()
        .setTitle(p.nome)
        .setDescription(p.desc || "Sem descrição.")
        .setColor(config.color)
        .setThumbnail(p.thumb || null)
        .setImage(p.banner || null);
    
    if (p.planos && p.planos.length > 0) {
        let planosText = "";
        p.planos.forEach(pl => {
            planosText += `🔹 **${pl.nome}**: R$ ${pl.preco} (Estoque: ${pl.estoque.length})\n`;
        });
        embed.addFields({ name: "📋 Planos Disponíveis", value: planosText });
    } else {
        embed.addFields({ name: "💰 Preço", value: `R$ ${p.preco}`, inline: true }, { name: "📦 Estoque", value: `${p.estoque.length}`, inline: true });
    }
    return embed;
};

// --- INTERAÇÕES ---
client.on('interactionCreate', async (interaction) => {
    if (interaction.user.id !== config.owner_id && !interaction.customId?.startsWith('buy_')) {
        if (interaction.isRepliable()) return interaction.reply({ content: "❌ Sem permissão.", ephemeral: true });
    }

    // 1. COMANDOS SLASH
    if (interaction.isChatInputCommand()) {
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
                new ButtonBuilder().setCustomId('conf_logs').setLabel('Canal de Logs').setStyle(ButtonStyle.Secondary),
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

        // COMPRA PELO CLIENTE
        if (action === 'buy' && sub === 'menu') {
            const p = db.get(`prod_${id}`);
            if (p.planos && p.planos.length > 0) {
                // Menu de seleção de planos (simplificado com botões para este código)
                const row = new ActionRowBuilder();
                p.planos.forEach((pl, index) => {
                    row.addComponents(new ButtonBuilder().setCustomId(`pay_plan_${id}_${index}`).setLabel(`${pl.nome} - R$ ${pl.preco}`).setStyle(ButtonStyle.Primary));
                });
                return interaction.reply({ content: "Escolha seu plano:", components: [row], ephemeral: true });
            }
            // Pagamento direto se não houver planos
            return generatePayment(interaction, id, p.preco, p.nome);
        }

        // GERENCIAMENTO PELO ADMIN
        if (action === 'manage' && sub === 'prod') {
            const p = db.get(`prod_${id}`);
            const embed = new EmbedBuilder().setTitle(`🛠️ Editando: ${p.nome}`).setColor(config.color);
            const row1 = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`edit_info_${id}`).setLabel('Editar Info').setStyle(ButtonStyle.Secondary),
                new ButtonBuilder().setCustomId(`add_plan_${id}`).setLabel('Add Plano').setStyle(ButtonStyle.Primary),
                new ButtonBuilder().setCustomId(`manage_stock_${id}`).setLabel('Estoque').setStyle(ButtonStyle.Success)
            );
            const row2 = new ActionRowBuilder().addComponents(
                new ButtonBuilder().setCustomId(`del_prod_${id}`).setLabel('Excluir Produto').setStyle(ButtonStyle.Danger)
            );
            await interaction.reply({ embeds: [embed], components: [row1, row2], ephemeral: true });
        }

        if (action === 'manage' && sub === 'stock') {
            const modal = new ModalBuilder().setCustomId(`modal_stock_${id}`).setTitle('Gerenciar Estoque');
            modal.addComponents(new ActionRowBuilder().addComponents(new TextInputBuilder().setCustomId('itens').setLabel('Cole os itens (um por linha)').setStyle(TextInputStyle.Paragraph).setRequired(true)));
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
                estoque: [], planos: [] 
            });
            await interaction.reply({ content: "✅ Produto criado com sucesso!", ephemeral: true });
        }

        if (interaction.customId === 'modal_pix') {
            const pix = interaction.fields.getTextInputValue('pix');
            db.set('config.pix', pix);
            config.pix_key = pix;
            await interaction.reply({ content: "✅ Chave PIX atualizada!", ephemeral: true });
        }

        if (interaction.customId.startsWith('modal_stock_')) {
            const id = interaction.customId.replace('modal_stock_', '');
            const itens = interaction.fields.getTextInputValue('itens').split('\n').filter(i => i.trim() !== "");
            const p = db.get(`prod_${id}`);
            p.estoque.push(...itens);
            db.set(`prod_${id}`, p);
            await interaction.reply({ content: `✅ ${itens.length} itens adicionados ao estoque!`, ephemeral: true });
        }
    }
});

async function generatePayment(interaction, id, preco, nome) {
    if (config.pix_key === "NÃO CONFIGURADO") return interaction.reply({ content: "❌ PIX não configurado.", ephemeral: true });
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
