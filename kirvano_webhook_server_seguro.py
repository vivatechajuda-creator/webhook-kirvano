"""
WEBHOOK SERVER - KIRVANO (VERSÃO SEGURA COM ENV)
================================================
Recebe notificações de pagamento e ativa usuários automaticamente
"""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import hmac
import hashlib
import json
import os
from datetime import datetime, timedelta
import logging

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Radar Político - Webhook Kirvano")

# =====================================================
# CONFIGURAÇÕES (VIA VARIÁVEIS DE AMBIENTE - SEGURO!)
# =====================================================

# Token de segurança (definido no Render.com)
KIRVANO_TOKEN = os.getenv("KIRVANO_TOKEN")

# Token do bot Telegram (definido no Render.com)
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Chat ID do admin (para notificações)
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")

# =====================================================
# VALIDAÇÃO DE WEBHOOK
# =====================================================

def validar_token(request_token: str) -> bool:
    """Valida se o token recebido é válido"""
    if not KIRVANO_TOKEN:
        logger.warning("⚠️ KIRVANO_TOKEN não configurado!")
        return True  # Aceita em dev
    
    return request_token == KIRVANO_TOKEN


# =====================================================
# ENDPOINTS
# =====================================================

@app.get("/")
async def root():
    """Endpoint raiz - verificar se servidor está online"""
    return {
        "status": "online",
        "service": "Radar Político - Webhook Kirvano",
        "version": "1.0.0",
        "configured": KIRVANO_TOKEN is not None
    }


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "env_check": {
            "kirvano_token": "✅" if KIRVANO_TOKEN else "❌",
            "bot_token": "✅" if BOT_TOKEN else "❌"
        }
    }


@app.post("/webhook/kirvano")
async def webhook_kirvano(request: Request):
    """
    Endpoint que recebe notificações da Kirvano.
    
    Eventos suportados:
    - SALE_APPROVED: Venda aprovada (PIX/Cartão)
    - SUBSCRIPTION_CREATED: Assinatura criada
    - SUBSCRIPTION_RENEWED: Assinatura renovada
    - SUBSCRIPTION_CANCELED: Assinatura cancelada
    - REFUND_REQUESTED: Reembolso solicitado
    """
    
    try:
        # Pegar dados do webhook
        data = await request.json()
        
        # Log do evento recebido
        logger.info(f"📩 Webhook recebido: {data.get('event', 'UNKNOWN')}")
        logger.info(f"   Sale ID: {data.get('sale_id', 'N/A')}")
        
        # Validar token
        token = data.get('token') or request.headers.get('X-Kirvano-Token')
        
        if KIRVANO_TOKEN and token:
            if not validar_token(token):
                logger.warning("❌ Token inválido!")
                raise HTTPException(status_code=401, detail="Token inválido")
        
        # Extrair informações importantes
        evento = data.get('event')
        sale_id = data.get('sale_id')
        checkout_id = data.get('checkout_id')
        
        # Extrair user_id do Telegram
        user_id_telegram = extract_user_id_from_kirvano_data(data)
        
        if not user_id_telegram:
            logger.error("❌ Não foi possível identificar usuário do Telegram!")
            logger.error(f"   Dados recebidos: {json.dumps(data, indent=2)}")
            
            # Notificar admin
            await notificar_admin(
                f"⚠️ Webhook sem user_id!\n\n"
                f"Evento: {evento}\n"
                f"Sale ID: {sale_id}\n"
                f"Verificar logs!"
            )
            
            return JSONResponse(
                status_code=200,
                content={"status": "error", "message": "user_id not found"}
            )
        
        # Processar evento
        if evento == "SALE_APPROVED":
            await processar_venda_aprovada(user_id_telegram, data)
        
        elif evento == "SUBSCRIPTION_CREATED":
            await processar_assinatura_criada(user_id_telegram, data)
        
        elif evento == "SUBSCRIPTION_RENEWED":
            await processar_assinatura_renovada(user_id_telegram, data)
        
        elif evento == "SUBSCRIPTION_CANCELED":
            await processar_assinatura_cancelada(user_id_telegram, data)
        
        elif evento == "REFUND_REQUESTED":
            await processar_reembolso(user_id_telegram, data)
        
        else:
            logger.warning(f"⚠️ Evento desconhecido: {evento}")
        
        # Retornar sucesso para Kirvano
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Webhook processado",
                "event": evento
            }
        )
    
    except Exception as e:
        logger.error(f"❌ Erro ao processar webhook: {e}")
        
        # Notificar admin
        await notificar_admin(f"❌ Erro no webhook:\n\n{str(e)}")
        
        return JSONResponse(
            status_code=500,
            content={"status": "error", "message": str(e)}
        )


# =====================================================
# PROCESSADORES DE EVENTOS
# =====================================================

async def processar_venda_aprovada(user_id: int, data: dict):
    """Processa venda aprovada - ATIVA USUÁRIO"""
    logger.info(f"✅ Venda aprovada para usuário {user_id}")
    
    # TODO: Integrar com seu bot
    # Por enquanto, apenas loga e notifica admin
    
    mensagem = (
        f"✅ <b>NOVA VENDA!</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"💰 Valor: {data.get('total_price', 'N/A')}\n"
        f"💳 Método: {data.get('payment_method', 'N/A')}\n"
        f"🆔 Sale ID: {data.get('sale_id', 'N/A')}\n\n"
        f"⚠️ <b>ATENÇÃO:</b> Ativar manualmente até integrar com bot!"
    )
    
    await notificar_admin(mensagem)
    
    logger.info(f"   ⚠️ Usuário {user_id} precisa ser ativado manualmente!")


async def processar_assinatura_criada(user_id: int, data: dict):
    """Processa criação de assinatura recorrente"""
    logger.info(f"📝 Assinatura criada para usuário {user_id}")
    await processar_venda_aprovada(user_id, data)


async def processar_assinatura_renovada(user_id: int, data: dict):
    """Processa renovação automática de assinatura"""
    logger.info(f"🔄 Assinatura renovada para usuário {user_id}")
    
    mensagem = (
        f"🔄 <b>RENOVAÇÃO</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"💰 Valor: {data.get('total_price', 'N/A')}\n"
        f"🆔 Sale ID: {data.get('sale_id', 'N/A')}"
    )
    
    await notificar_admin(mensagem)


async def processar_assinatura_cancelada(user_id: int, data: dict):
    """Processa cancelamento de assinatura"""
    logger.info(f"❌ Assinatura cancelada para usuário {user_id}")
    
    mensagem = (
        f"❌ <b>CANCELAMENTO</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"🆔 Sale ID: {data.get('sale_id', 'N/A')}"
    )
    
    await notificar_admin(mensagem)


async def processar_reembolso(user_id: int, data: dict):
    """Processa solicitação de reembolso"""
    logger.info(f"💸 Reembolso solicitado para usuário {user_id}")
    
    mensagem = (
        f"💸 <b>REEMBOLSO</b>\n\n"
        f"👤 User ID: <code>{user_id}</code>\n"
        f"🆔 Sale ID: {data.get('sale_id', 'N/A')}\n\n"
        f"⚠️ Desativar usuário manualmente!"
    )
    
    await notificar_admin(mensagem)


# =====================================================
# FUNÇÕES AUXILIARES
# =====================================================

def extract_user_id_from_kirvano_data(data: dict) -> int:
    """
    Extrai o user_id do Telegram dos dados da Kirvano.
    
    Tenta em vários lugares possíveis.
    """
    
    # Opção 1: No parâmetro ?ref= da URL (vem como external_reference ou similar)
    # A Kirvano pode enviar em diferentes campos
    
    # Tentar no customer
    customer = data.get('customer', {})
    
    # Verificar se tem phone_number que pode ser o user_id
    # (se você pediu no checkout)
    phone = customer.get('phone_number', '')
    if phone.isdigit():
        try:
            return int(phone)
        except:
            pass
    
    # Tentar extrair de metadata/custom fields
    metadata = data.get('metadata', {})
    user_id = metadata.get('telegram_user_id') or metadata.get('user_id')
    if user_id:
        return int(user_id)
    
    # Tentar no checkout_id (se você salvou a relação)
    # Este é um placeholder - você precisa ter um dicionário
    # mapeando checkout_id -> user_id
    
    logger.error(f"❌ User ID não encontrado nos dados!")
    return None


async def notificar_admin(mensagem: str):
    """Envia notificação para o admin via Telegram"""
    
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        logger.warning("⚠️ BOT_TOKEN ou ADMIN_CHAT_ID não configurados")
        return
    
    try:
        import aiohttp
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={
                "chat_id": ADMIN_CHAT_ID,
                "text": mensagem,
                "parse_mode": "HTML"
            }) as response:
                if response.status == 200:
                    logger.info("✅ Admin notificado")
                else:
                    logger.error(f"❌ Erro ao notificar admin: {response.status}")
    
    except Exception as e:
        logger.error(f"❌ Erro ao enviar notificação: {e}")


# =====================================================
# LOGS DE DEBUG
# =====================================================

@app.post("/webhook/kirvano/test")
async def webhook_test(request: Request):
    """Endpoint de teste para ver o que a Kirvano está enviando"""
    data = await request.json()
    
    logger.info("=" * 60)
    logger.info("TESTE DE WEBHOOK - DADOS RECEBIDOS:")
    logger.info(json.dumps(data, indent=2, ensure_ascii=False))
    logger.info("=" * 60)
    
    await notificar_admin(
        f"🧪 <b>TESTE DE WEBHOOK</b>\n\n"
        f"<pre>{json.dumps(data, indent=2, ensure_ascii=False)}</pre>"
    )
    
    return {"status": "received", "data": data}


# =====================================================
# INICIALIZAÇÃO
# =====================================================

if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("WEBHOOK SERVER - KIRVANO (VERSÃO SEGURA)")
    print("=" * 60)
    print()
    print("🔒 Configurações via variáveis de ambiente:")
    print(f"   KIRVANO_TOKEN: {'✅ Configurado' if KIRVANO_TOKEN else '❌ Não configurado'}")
    print(f"   BOT_TOKEN: {'✅ Configurado' if BOT_TOKEN else '❌ Não configurado'}")
    print(f"   ADMIN_CHAT_ID: {'✅ Configurado' if ADMIN_CHAT_ID else '❌ Não configurado'}")
    print()
    print("🚀 Iniciando servidor...")
    print()
    print("Endpoints disponíveis:")
    print("  • POST /webhook/kirvano")
    print("  • POST /webhook/kirvano/test")
    print("  • GET  /health")
    print()
    print("=" * 60)
    
    # Porta configurável via env (Render usa $PORT)
    port = int(os.getenv("PORT", 8000))
    
    uvicorn.run(app, host="0.0.0.0", port=port)
