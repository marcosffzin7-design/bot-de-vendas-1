const axios = require("axios")
const config = require("./token.json")
const { Client, GatewayIntentBits, Collection, EmbedBuilder, ActivityType } = require("discord.js");
const { readdirSync } = require("node:fs")
const { JsonDatabase } = require("wio.db");
const { getCache } = require("./Functions/connect_api");
const dbPerms = new JsonDatabase({ databasePath: "./databases/dbPermissions.json" });
const dbDataTickets = new JsonDatabase({ databasePath: "./databases/data_ticket.json" })
const dbConfigs = new JsonDatabase({ databasePath: "./databases/dbConfigs.json" });

const client = new Client({
    intents: [
        GatewayIntentBits.Guilds,
        GatewayIntentBits.GuildMessages,
        GatewayIntentBits.GuildMembers,
        GatewayIntentBits.GuildMessageReactions,
        GatewayIntentBits.MessageContent,
        GatewayIntentBits.DirectMessages
    ]
});

client.commands = new Collection();
const handlers = readdirSync("./src/handler").filter((file) => file.endsWith('.js'));
for (const file of handlers) {
    require(`./src/handler/${file}`)(client);
};
client.handleCommands("./src/slashCommands");

client.on('guildBanRemove', (ban) => {
    console.log(`guildBanRemove: ${ban}`);
});

client.once('ready', async () => {
    if (dbConfigs.get('dbRedefine') === false || dbConfigs.get('dbRedefine') === null) {
        dbConfigs.set('ticket.ticket.cargo_staff', [])
        dbConfigs.set('dbRedefine', true)
    }

    const guilds = client.guilds.cache;
    try {
        guilds.forEach(async guild => {
            const allData = dbDataTickets.all();
            let totalCanais = 0
            for (const key in allData) {
                const channelID = allData[key].ID
                const channel = guild.channels.cache.get(channelID);
                if (!channel) {
                    totalCanais++
                    dbDataTickets.delete(channelID);
                }
            }
        });
    } catch (error) {
        console.log(error)
    }

    

    /**
     * @typedef {Object} CacheData
     * @property {string} [status] - Status atual do cache
     */

    /**
     * Atualiza a presença e descrição do bot Discord
     * @returns {Promise<void>}
     */
    const updateBotProfile = async () => {
        try {
            // Obter dados do cache com tratamento de tipo
            /** @type {CacheData|false} */
            const cacheData = getCache(null, 'additional');
            //console.log('Cache data:', cacheData);

            // Verificar se o cache está disponível
            if (cacheData === false) {
                console.log('Cache não disponível, tentando novamente em 20 segundos');
                setTimeout(updateBotProfile, 20000);
                return;
            }

            // Verificar se a atualização é necessária
            if (!Array.isArray(cacheData) || !cacheData.includes('status')) {
                await Promise.all([
                    updateBotPresence(),
                    updateBotDescription()
                ]);
            }
        } catch (error) {
            console.error('Erro ao atualizar perfil do bot:', error);
        }
    };

    /**
     * Atualiza a presença do bot no Discord
     * @returns {Promise<void>}
     */
    const updateBotPresence = async () => {
        try {
            client.user.setPresence({
                activities: [{
                    name: '🤖  Applications',
                    type: ActivityType.Custom
                }],
                status: 'online',
            });
            //console.log('Presença do bot atualizada com sucesso');
        } catch (error) {
            console.error('Erro ao atualizar presença:', error);
        }
    };

    /**
     * Atualiza a descrição do bot via API Discord
     * @returns {Promise<void>}
     */
    const updateBotDescription = async () => {
        // Descrição formatada do bot
        const description = [
            "**SZZ Store!**",
            "https://szzstore.shop"
        ].join('\n');

        // Dados para atualização
        const updateData = {
            description,
            custom_install_url: "https://discord.gg/ZVERbrk2HD",
            install_params: null
        };

        try {
            const url = `https://discord.com/api/v9/applications/${client.user.id}`;
            const response = await fetch(url, {
                method: "PATCH",
                headers: {
                    Authorization: `Bot ${config.token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(updateData),
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({}));
                throw new Error(`API retornou status ${response.status}: ${JSON.stringify(errorData)}`);
            }

            //console.log('Descrição do bot atualizada com sucesso');
        } catch (error) {
            //console.error('Erro ao atualizar descrição:', error);
            // Implementação de retry com backoff exponencial seria ideal aqui
        }
    };

    // Configuração de execução inicial e periódica
    const THIRTY_MINUTES = 60000 * 30;

    // Executar imediatamente
    updateBotProfile();

    // Configurar execução periódica
    const intervalId = setInterval(updateBotProfile, THIRTY_MINUTES);

    // Armazenar o intervalId em uma propriedade do cliente para acesso global
    client.profileUpdateInterval = intervalId;

    // Definir função de limpeza como método do cliente
    client.cleanupProfileUpdater = () => {
        if (client.profileUpdateInterval) {
            clearInterval(client.profileUpdateInterval);
            client.profileUpdateInterval = null;
            //console.log('Limpeza do atualizador de perfil realizada');
        }
    };

    try {
        const getMember = await client.users.fetch(getCache(null, 'owner'));
        if (client.guilds.cache.size > 1) {
            const embedSend = new EmbedBuilder()
                .setTitle('❗ | Servidores em excesso.')
                .setDescription([
                    `- Olá ${getMember}!`,
                    `- Percebemos que sua aplicação estava em mais de 1 servidor e isso não é permitido por nossa equipe.`,
                    `- Caso queira adiciona-la em mais de um servidor compre outra permissão.`,
                    `- Caso isso tenha ocorrido sem sua permissão contate nosso suporte em: https://ptb.discord.com/channels/1361460945565647091/1384688390917591110.`,
                    `\u200b`,
                    `- Caso tenha saido do nosso servidor (CLIQUE AQUI)[https://discord.gg/ZVERbrk2HD]`
                ].join('\n'))
                .setColor(0xFF0000)
                .setFooter({ text: `SZZ Store - Todos os direitos reservados.` })

            await getMember.send({ embeds: [embedSend] })
            for (const guild of guilds.values()) {
                try {
                    await guild.leave();
                    console.log(`Saí do servidor: ${guild.name}`);
                } catch (error) {
                    console.error(`Erro ao sair do servidor ${guild.name}:`, error);
                }
            }
        }
    } catch (error) {
        if (error.code === 50035) {
            return
        } else {
            console.log(`${error}`)
        }
    }
});

client.on('guildCreate', async guild => {
    console.log(`Bot entrou em um novo servidor: ${guild.name}.`);

    try {
        const getMember = await client.users.fetch(getCache(null, 'owner'))

        if (client.guilds.cache.size > 1) {
            try {
                await getMember.send({ content: `❗ | Houve uma tentativa de adicionar sua aplicação em outro servidor, por questões de segurança a aplicação saiu desse servidor.\n⏩ | Servidor em questão **${guild.name}**.` })
            } catch (error) {
                console.error(`Descrição do erro: ${error}`)
            }
            guild.leave()
                .then(() => console.log(`Saiu do servidor ${guild.name}`))
                .catch(console.error);
        }
    } catch (error) {
        if (error.code === 50035) {
            console.log()
        } else {
            console.log(`${error.message}`)
        }
    }
});

client.on('messageCreate', async (message) => {
    if (message.author.bot) return;
    const { JsonDatabase } = require("wio.db")
    const dbConfigs = new JsonDatabase({ databasePath: "./databases/dbConfigs.json" })
    if (dbConfigs.get(`ticket.sugest.sistema`) === "ON") {
        const channelId = dbConfigs.get(`ticket.sugest.channel`)
        if (message.channel.id === channelId) {
            await message.react(dbConfigs.get(`ticket.sugest.certo`) || '✔')
            await message.react(dbConfigs.get(`ticket.sugest.errado`) || '❌')
            const user = message.author;

            const thread = await message.startThread({
                name: `Sugestão de ${user.displayName}`,
                autoArchiveDuration: 10080,
                reason: `Sugestão de ${user.displayName}`
            });
            await thread.send(`Olá ${user} 👋, obrigado por enviar sua sugestão! Caso necessário, explique melhor a mesma.`);
        }
    }

});

function handleError(error, origin) {
    console.error(`\n--------------------------------`);
    console.error(`Error occurred: ${error.message}`);
    console.error(`Origin: ${origin}`);
    console.error('Stack Trace:\n', error.stack);
    console.error(`--------------------------------\n`);
}

process.on('multipleResolves', (error, origin) => {
    handleError(error, origin);
});
process.on('unhandledRejection', (error, origin) => {
    handleError(error, origin);
});
process.on('uncaughtException', (error, origin) => {
    handleError(error, origin);
});
process.on('uncaughtExceptionMonitor', (error, origin) => {
    handleError(error, origin);
});
module.exports = client;
client.login(config.token);
// 1. Importar o Express
const express = require('express');
const app = express();

// 2. Configurar o servidor da API
app.use(express.json());
app.use((req, res, next) => {
    res.header('Access-Control-Allow-Origin', '*');
    res.header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE');
    res.header('Access-Control-Allow-Headers', 'Content-Type');
    next();
});

// 3. Banco de dados do dashboard (em memória)
let dashboardData = {
    sales: [],
    products: [
        { id: 1, name: 'VIP Mensal', price: 49.90, stock: 999, totalSales: 0 },
        { id: 2, name: 'VIP Semanal', price: 19.90, stock: 999, totalSales: 0 },
        { id: 3, name: 'Boost XP', price: 29.90, stock: 500, totalSales: 0 },
        { id: 4, name: 'Cargo Especial', price: 99.90, stock: 100, totalSales: 0 }
    ],
    customers: new Map()
};

// 4. ENDPOINTS DA API DO DASHBOARD
app.get('/api/health', (req, res) => {
    res.json({ status: 'online', timestamp: new Date() });
});

app.get('/api/stats', (req, res) => {
    const totalSales = dashboardData.sales.length;
    const totalRevenue = dashboardData.sales.reduce((sum, sale) => sum + sale.amount, 0);
    const uniqueCustomers = new Set(dashboardData.sales.map(s => s.discordId)).size;
    const avgTicket = totalSales > 0 ? totalRevenue / totalSales : 0;
    
    res.json({ totalSales, totalRevenue, totalCustomers: uniqueCustomers, avgTicket });
});

app.get('/api/sales', (req, res) => {
    res.json(dashboardData.sales.sort((a,b) => new Date(b.date) - new Date(a.date)));
});

app.get('/api/products', (req, res) => {
    res.json(dashboardData.products);
});

app.get('/api/customers', (req, res) => {
    const customersList = Array.from(dashboardData.customers.values());
    res.json(customersList);
});

// 5. Endpoint para registrar novas vendas
app.post('/api/new-sale', (req, res) => {
    const { customerTag, discordId, product, amount, status, productId } = req.body;
    
    const newSale = {
        id: Date.now(),
        customer: customerTag,
        discordId: discordId,
        product: product,
        amount: amount,
        status: status || 'completed',
        date: new Date().toISOString(),
        productId: productId
    };
    
    dashboardData.sales.push(newSale);
    
    // Atualizar dados do cliente
    if (discordId) {
        const existingCustomer = dashboardData.customers.get(discordId);
        if (existingCustomer) {
            existingCustomer.totalSpent = (existingCustomer.totalSpent || 0) + amount;
            existingCustomer.purchases = (existingCustomer.purchases || 0) + 1;
            existingCustomer.lastPurchase = new Date().toISOString();
            dashboardData.customers.set(discordId, existingCustomer);
        } else {
            dashboardData.customers.set(discordId, {
                discordId: discordId,
                tag: customerTag,
                totalSpent: amount,
                purchases: 1,
                lastPurchase: new Date().toISOString()
            });
        }
    }
    
    // Atualizar estatísticas do produto
    const productIndex = dashboardData.products.findIndex(p => p.id === productId);
    if (productIndex !== -1) {
        dashboardData.products[productIndex].totalSales = (dashboardData.products[productIndex].totalSales || 0) + 1;
    }
    
    console.log(`✅ Nova venda registrada no dashboard: ${customerTag} - ${product} - R$ ${amount}`);
    res.json({ success: true, sale: newSale });
});

// 6. FUNÇÃO PARA REGISTRAR VENDA (use isso nos seus comandos)
async function registerSaleToDashboard(saleData) {
    try {
        const fetch = require('node-fetch');
        const response = await fetch('http://localhost:3000/api/new-sale', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(saleData)
        });
        return await response.json();
    } catch (error) {
        console.error('Erro ao registrar venda no dashboard:', error);
    }
}

// 7. Iniciar o servidor da API
const PORT = 3000;
app.listen(PORT, () => {
    console.log(`📊 Dashboard API rodando em http://localhost:${PORT}`);
    console.log(`🔗 Dashboard disponível em: http://localhost:${PORT}/dashboard.html`);
});

// ============================================
// SEUS COMANDOS EXISTENTES DO BOT
// ============================================

// EXEMPLO: Comando de venda que REGISTRA no dashboard
client.on('messageCreate', async (message) => {
    if (message.content.startsWith('!comprar')) {
        const args = message.content.split(' ');
        const productName = args[1];
        
        // LÓGICA DA SUA VENDA AQUI...
        
        // 🔥 DEPOIS DE PROCESSAR A VENDA, REGISTRE NO DASHBOARD:
        await registerSaleToDashboard({
            customerTag: message.author.tag,
            discordId: message.author.id,
            product: 'VIP Mensal', // ou o produto que foi comprado
            amount: 49.90, // valor da venda
            status: 'completed',
            productId: 1 // ID do produto
        });
        
        await message.reply('✅ Compra realizada e registrada no dashboard!');
    }
});

// EXEMPLO COM SLASH COMMANDS (se você usar)
client.on('interactionCreate', async (interaction) => {
    if (!interaction.isCommand()) return;
    
    if (interaction.commandName === 'comprar') {
        const produto = interaction.options.getString('produto');
        
        // LÓGICA DA SUA VENDA...
        
        // 🔥 REGISTRAR NO DASHBOARD:
        await registerSaleToDashboard({
            customerTag: interaction.user.tag,
            discordId: interaction.user.id,
            product: produto,
            amount: 49.90,
            status: 'completed',
            productId: 1
        });
        
        await interaction.reply('✅ Venda registrada com sucesso!');
    }
});

// ============================================
// INICIAR O BOT
// ============================================
client.once('ready', () => {
    console.log(`🤖 Bot ${client.user.tag} está online!`);
    console.log(`📊 Dashboard disponível em http://localhost:3000`);
});

client.login(TOKEN);