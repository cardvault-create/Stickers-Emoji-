import os
import json
import logging
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '8799309309:AAEy_csS6ESN8NObQlxHMss5YPmYEGOEtcc')
DATA_FILE = 'pack_data.json'

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                data = json.load(f)
                data.setdefault('sticker_packs', {})
                data.setdefault('user_packs', {})
                return data
    except Exception:
        pass
    return {'sticker_packs': {}, 'user_packs': {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

data = load_data()
user_states = {}
pending_stickers = {}  # Store stickers before pack creation

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Create Sticker Pack", callback_data='create_sticker')],
        [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global data
    data = load_data()
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text("👋 Welcome! Choose an option:", reply_markup=get_main_menu())
    else:
        await update.message.reply_text("👋 Welcome! Choose an option:", reply_markup=get_main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global data
    data = load_data()
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == 'create_sticker':
        await query.edit_message_text(
            "📦 Create Sticker Pack\n\nSend me a name (English letters, digits, underscores).\n"
            "Must end with '_by_<your_bot_username>'\nExample: `my_pack_by_MyBot`\n\n"
            "Then send stickers (PNG/WEBP) - I'll collect them and create pack!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
        user_states[user_id] = 'awaiting_sticker_name'
        pending_stickers[user_id] = []
    
    elif query.data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif query.data == 'help':
        await query.edit_message_text(
            "ℹ️ How it works:\n\n"
            "1. Click 'Create Sticker Pack'\n"
            "2. Send pack name (must end with '_by_botusername')\n"
            "3. Send PNG/WEBP stickers (max 120)\n"
            "4. Send /publish to create the pack!\n\n"
            "⚠️ Bot API can't create emoji packs - use @Emoji bot for that.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
    
    elif query.data == 'back_to_main':
        await start(update, context)
    
    elif query.data.startswith('view_pack_'):
        pack_name = query.data.replace('view_pack_', '')
        await view_pack(update, context, user_id, pack_name)
    
    elif query.data.startswith('delete_pack_'):
        pack_name = query.data.replace('delete_pack_', '')
        await delete_pack(update, context, user_id, pack_name)

async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    query = update.callback_query
    user_packs = data['user_packs'].get(user_id, [])
    
    if not user_packs:
        await query.edit_message_text("📭 No packs yet!", reply_markup=get_main_menu())
        return
    
    keyboard = [[InlineKeyboardButton(f"📦 {p}", callback_data=f'view_pack_{p}')] for p in user_packs]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_main')])
    await query.edit_message_text("📋 Your Packs:", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = data['sticker_packs'].get(pack_name)
    
    if not pack or pack.get('creator') != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='my_packs')]]))
        return
    
    keyboard = [
        [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')],
        [InlineKeyboardButton("🗑️ Delete Pack", callback_data=f'delete_pack_{pack_name}')],
        [InlineKeyboardButton("🔙 Back", callback_data='my_packs')]
    ]
    await query.edit_message_text(
        f"📦 {pack_name}\nStickers: {len(pack.get('items', []))}\nLink: {pack.get('link', 'Not created')}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    if pack_name in data['sticker_packs']:
        del data['sticker_packs'][pack_name]
    if user_id in data['user_packs'] and pack_name in data['user_packs'][user_id]:
        data['user_packs'][user_id].remove(pack_name)
    save_data(data)
    await query.edit_message_text("✅ Deleted!", reply_markup=get_main_menu())

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global data
    data = load_data()
    user_id = str(update.effective_user.id)
    message = update.message
    
    if user_id not in user_states:
        await message.reply_text("Use /start first!")
        return
    
    state = user_states[user_id]
    
    # Handle pack name
    if state == 'awaiting_sticker_name':
        pack_name = message.text.strip().replace(' ', '_')
        # Must end with _by_botusername
        bot_username = context.bot.username
        expected_suffix = f"_by_{bot_username}"
        
        if not pack_name.endswith(expected_suffix):
            await message.reply_text(f"❌ Name must end with '{expected_suffix}'\nExample: my_pack{expected_suffix}")
            return
        
        if pack_name in data['sticker_packs']:
            await message.reply_text("❌ Pack name already exists!")
            return
        
        # Save pack name and switch to collecting stickers
        user_states[user_id] = 'collecting_stickers'
        pending_stickers[user_id] = {'name': pack_name, 'stickers': [], 'title': pack_name.replace('_', ' ').title()}
        await message.reply_text(f"✅ Pack name: {pack_name}\nNow send PNG/WEBP stickers!\nType /publish when done.")
        return
    
    # Collect stickers
    if state == 'collecting_stickers':
        file_id = None
        sticker_type = None
        
        if message.document:
            doc = message.document
            if doc.mime_type in ['image/png', 'image/webp']:
                file_id = doc.file_id
                sticker_type = 'png_sticker' if doc.mime_type == 'image/png' else 'webp_sticker'
        
        if not file_id:
            await message.reply_text("❌ Send PNG or WEBP file as document!")
            return
        
        pending_stickers[user_id]['stickers'].append({'file_id': file_id, 'type': sticker_type})
        await message.reply_text(f"✅ Added! ({len(pending_stickers[user_id]['stickers'])}/120)\nSend more or /publish")

async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if user_id not in pending_stickers or 'stickers' not in pending_stickers[user_id]:
        await update.message.reply_text("❌ No stickers collected! Start with /start")
        return
    
    pack_info = pending_stickers[user_id]
    stickers = pack_info['stickers']
    pack_name = pack_info['name']
    
    if not stickers:
        await update.message.reply_text("❌ Send at least 1 sticker!")
        return
    
    # Create sticker pack via Bot API
    try:
        bot_username = context.bot.username
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
        
        # First sticker
        first = stickers[0]
        files = {first['type']: (f'sticker.{first["type"].split("_")[0]}', requests.get(first['file_id']).content)}
        
        data = {
            'user_id': int(user_id),
            'name': pack_name,
            'title': pack_info['title'],
            'emojis': '😀'  # Default emoji
        }
        
        response = requests.post(api_url, data=data, files=files)
        result = response.json()
        
        if not result.get('ok'):
            await update.message.reply_text(f"❌ Error: {result}")
            return
        
        # Add remaining stickers
        for sticker in stickers[1:]:
            add_url = f"https://api.telegram.org/bot{TOKEN}/addStickerToSet"
            files = {sticker['type']: (f'sticker.{sticker["type"].split("_")[0]}', requests.get(sticker['file_id']).content)}
            add_data = {
                'user_id': int(user_id),
                'name': pack_name,
                'emojis': '😀'
            }
            requests.post(add_url, data=add_data, files=files)
        
        # Save to data
        data['sticker_packs'][pack_name] = {
            'creator': user_id,
            'items': stickers,
            'link': f"https://t.me/addstickers/{pack_name}",
            'created': datetime.now().isoformat()
        }
        data['user_packs'].setdefault(user_id, []).append(pack_name)
        save_data(data)
        
        del pending_stickers[user_id]
        del user_states[user_id]
        
        await update.message.reply_text(
            f"✅ Sticker pack created!\n\nLink: https://t.me/addstickers/{pack_name}\n\nTotal stickers: {len(stickers)}",
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
    if user_id in pending_stickers:
        del pending_stickers[user_id]
    await update.message.reply_text("❌ Cancelled!", reply_markup=get_main_menu())

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("publish", publish))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    app.run_polling()

if __name__ == '__main__':
    main()
