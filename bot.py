import os
import json
import logging
import sqlite3
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '8799309309:AAEy_csS6ESN8NObQlxHMss5YPmYEGOEtcc')
DATABASE = 'packs.db'

# Database functions
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS sticker_packs
                 (pack_name TEXT PRIMARY KEY, creator TEXT, items TEXT, 
                  published INTEGER, link TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_packs
                 (user_id TEXT, pack_type TEXT, pack_name TEXT,
                  PRIMARY KEY (user_id, pack_type, pack_name))''')
    conn.commit()
    conn.close()

def get_pack(pack_type, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    if pack_type == 'sticker':
        c.execute("SELECT * FROM sticker_packs WHERE pack_name=?", (pack_name,))
    else:
        c.execute("SELECT * FROM sticker_packs WHERE pack_name=?", (pack_name,))
    row = c.fetchone()
    conn.close()
    if row:
        return {'pack_name': row[0], 'creator': row[1], 'items': json.loads(row[2]) if row[2] else [],
                'published': bool(row[3]), 'link': row[4], 'created': row[5]}
    return None

def save_pack(pack_type, pack_name, data):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    items_json = json.dumps(data.get('items', []))
    c.execute('''INSERT OR REPLACE INTO sticker_packs 
                 (pack_name, creator, items, published, link, created)
                 VALUES (?, ?, ?, ?, ?, ?)''',
              (pack_name, data['creator'], items_json, 
               1 if data.get('published', False) else 0,
               data.get('link', ''), data.get('created', datetime.now().isoformat())))
    conn.commit()
    conn.close()

def delete_pack_db(pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM sticker_packs WHERE pack_name=?", (pack_name,))
    c.execute("DELETE FROM user_packs WHERE pack_name=?", (pack_name,))
    conn.commit()
    conn.close()

def get_user_packs(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT pack_name FROM user_packs WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    return [row[0] for row in rows]

def add_user_pack(user_id, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_packs (user_id, pack_type, pack_name) VALUES (?, ?, ?)",
              (user_id, 'sticker', pack_name))
    conn.commit()
    conn.close()

def remove_user_pack(user_id, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM user_packs WHERE user_id=? AND pack_name=?", (user_id, pack_name))
    conn.commit()
    conn.close()

init_db()
user_states = {}
pending_packs = {}

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Create Sticker Pack", callback_data='create_sticker')],
        [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "👋 **Welcome!**\n\n"
            "✅ Create sticker packs with photos, videos, stickers\n"
            "⚠️ Pack name must end with `_by_botusername`\n"
            "📌 First sticker must be a PNG image",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )
    else:
        await update.message.reply_text(
            "👋 **Welcome!**\n\n"
            "✅ Create sticker packs with photos, videos, stickers\n"
            "⚠️ Pack name must end with `_by_botusername`\n"
            "📌 First sticker must be a PNG image",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == 'create_sticker':
        bot_username = context.bot.username
        await query.edit_message_text(
            f"📦 **Create Sticker Pack**\n\n"
            f"Send pack name (must end with `_by_{bot_username}`)\n"
            f"Example: `my_pack_by_{bot_username}`\n\n"
            f"Then send PNG/WEBP stickers\n"
            f"Type /publish when done",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
        user_states[user_id] = 'awaiting_sticker_name'
        pending_packs[user_id] = {'items': []}
    
    elif query.data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif query.data == 'help':
        await query.edit_message_text(
            "ℹ️ **How it works:**\n\n"
            "1. Click 'Create Sticker Pack'\n"
            "2. Send pack name (must end with _by_botusername)\n"
            "3. Send PNG images as documents\n"
            "4. Type /publish to create pack!\n\n"
            "⚠️ First sticker MUST be PNG format",
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
    
    elif query.data.startswith('get_link_'):
        pack_name = query.data.replace('get_link_', '')
        await get_pack_link(update, context, user_id, pack_name)

async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    query = update.callback_query
    packs = get_user_packs(user_id)
    
    if not packs:
        await query.edit_message_text("📭 No packs yet!", reply_markup=get_main_menu())
        return
    
    keyboard = [[InlineKeyboardButton(f"📦 {p}", callback_data=f'view_pack_{p}')] for p in packs]
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_main')])
    await query.edit_message_text("📋 Your Packs:", reply_markup=InlineKeyboardMarkup(keyboard))

async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack('sticker', pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='my_packs')]]))
        return
    
    items = len(pack.get('items', []))
    published = pack.get('published', False)
    
    keyboard = [
        [InlineKeyboardButton("📤 Add Sticker", callback_data=f'add_to_pack_{pack_name}')],
        [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')],
        [InlineKeyboardButton("🗑️ Delete Pack", callback_data=f'delete_pack_{pack_name}')],
        [InlineKeyboardButton("🔙 Back", callback_data='my_packs')]
    ]
    
    status = "✅ Published" if published else "⏳ Draft"
    await query.edit_message_text(
        f"📦 {pack_name}\nStatus: {status}\nItems: {items}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack('sticker', pack_name)
    if pack and pack['creator'] == user_id:
        delete_pack_db(pack_name)
        remove_user_pack(user_id, pack_name)
        await query.edit_message_text("✅ Deleted!", reply_markup=get_main_menu())
    else:
        await query.edit_message_text("❌ Pack not found!")

async def get_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack('sticker', pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!")
        return
    
    link = f"https://t.me/addstickers/{pack_name}"
    published = pack.get('published', False)
    
    if published:
        msg = f"✅ **Published!**\n\n🔗 `{link}`"
    else:
        msg = f"⏳ **Not published yet!**\n\n"
        msg += f"📦 Name: `{pack_name}`\n"
        msg += f"📊 Items: {len(pack.get('items', []))}\n\n"
        msg += f"After publishing: `{link}`"
    
    await query.edit_message_text(
        msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    # Creating new pack
    if user_id in user_states and user_states[user_id] == 'awaiting_sticker_name':
        pack_name = message.text.strip().replace(' ', '_')
        bot_username = context.bot.username
        expected_suffix = f"_by_{bot_username}"
        
        if not pack_name.endswith(expected_suffix):
            await message.reply_text(f"❌ Name must end with '{expected_suffix}'")
            return
        
        if get_pack('sticker', pack_name):
            await message.reply_text("❌ Pack name already exists!")
            return
        
        # Create pack
        data = {'creator': user_id, 'items': [], 'published': False, 
                'link': f"https://t.me/addstickers/{pack_name}",
                'created': datetime.now().isoformat()}
        save_pack('sticker', pack_name, data)
        add_user_pack(user_id, pack_name)
        
        del user_states[user_id]
        pending_packs[user_id] = {'name': pack_name, 'items': []}
        
        await message.reply_text(
            f"✅ Pack created!\n\nSend **PNG** files as documents.\nType /publish when done.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')]])
        )
        return
    
    # Adding stickers to pack
    if user_id in pending_packs:
        pack_name = pending_packs[user_id].get('name')
        if not pack_name:
            return
        
        # Handle document (PNG file)
        if message.document:
            doc = message.document
            if doc.mime_type in ['image/png', 'image/webp']:
                pending_packs[user_id]['items'].append({
                    'type': 'png_sticker' if doc.mime_type == 'image/png' else 'webp_sticker',
                    'file_id': doc.file_id
                })
                await message.reply_text(f"✅ Added! ({len(pending_packs[user_id]['items'])} stickers)")
            else:
                await message.reply_text("❌ Send PNG or WEBP file!")
        else:
            await message.reply_text("❌ Send file as document!")
        return
    
    await message.reply_text("Use /start to begin!")

async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    if user_id not in pending_packs:
        await update.message.reply_text("❌ No pack in progress! Use /start")
        return
    
    pack_info = pending_packs[user_id]
    pack_name = pack_info.get('name')
    items = pack_info.get('items', [])
    
    if not items:
        await update.message.reply_text("❌ Add at least 1 sticker first!")
        return
    
    try:
        bot_username = context.bot.username
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
        
        # Get first sticker (MUST be PNG)
        first = items[0]
        file_id = first['file_id']
        file_info = await context.bot.get_file(file_id)
        file_content = await file_info.download_as_bytearray()
        
        # Check if first sticker is PNG
        if first['type'] != 'png_sticker':
            await update.message.reply_text(
                "❌ **First sticker MUST be PNG format!**\n\n"
                "Send a PNG image first, then other formats."
            )
            return
        
        # Create pack with first sticker
        params = {
            'user_id': int(user_id),
            'name': pack_name,
            'title': pack_name.replace('_', ' ').title(),
            'emojis': '😀'
        }
        files = {'png_sticker': ('sticker.png', file_content)}
        
        response = requests.post(api_url, data=params, files=files)
        result = response.json()
        
        if not result.get('ok'):
            error_msg = str(result)
            if 'name is already occupied' in error_msg:
                # Update existing pack
                pack_data = get_pack('sticker', pack_name)
                if pack_data:
                    pack_data['published'] = True
                    save_pack('sticker', pack_name, pack_data)
                    await update.message.reply_text(
                        f"✅ **Pack already exists!**\n\n"
                        f"🔗 `https://t.me/addstickers/{pack_name}`",
                        parse_mode=ParseMode.MARKDOWN
                    )
                    del pending_packs[user_id]
                    return
            else:
                await update.message.reply_text(f"❌ Error: {error_msg}")
                return
        
        # Add remaining stickers
        for item in items[1:]:
            file_id = item['file_id']
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            sticker_type = item['type']  # png_sticker or webp_sticker
            add_url = f"https://api.telegram.org/bot{TOKEN}/addStickerToSet"
            add_params = {
                'user_id': int(user_id),
                'name': pack_name,
                'emojis': '😀'
            }
            add_files = {sticker_type: ('sticker', file_content)}
            requests.post(add_url, data=add_params, files=add_files)
        
        # Update database
        pack_data = get_pack('sticker', pack_name)
        if pack_data:
            pack_data['published'] = True
            save_pack('sticker', pack_name, pack_data)
        
        link = f"https://t.me/addstickers/{pack_name}"
        await update.message.reply_text(
            f"✅ **Sticker pack created!**\n\n"
            f"📦 {pack_name}\n"
            f"📊 {len(items)} stickers\n"
            f"🔗 `{link}`\n\n"
            f"**Click the link to add to Telegram!**",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )
        
        del pending_packs[user_id]
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
    if user_id in pending_packs:
        del pending_packs[user_id]
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
