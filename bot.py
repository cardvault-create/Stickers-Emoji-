import os
import json
import logging
import sqlite3
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', '8799309309:AAEy_csS6ESN8NObQlxHMss5YPmYEGOEtcc')
DATABASE = 'packs.db'

# Database functions
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    # Create tables
    c.execute('''CREATE TABLE IF NOT EXISTS sticker_packs
                 (pack_name TEXT PRIMARY KEY, creator TEXT, items TEXT, 
                  published INTEGER, link TEXT, created TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS emoji_packs
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
        c.execute("SELECT * FROM emoji_packs WHERE pack_name=?", (pack_name,))
    
    row = c.fetchone()
    conn.close()
    
    if row:
        return {
            'pack_name': row[0],
            'creator': row[1],
            'items': json.loads(row[2]) if row[2] else [],
            'published': bool(row[3]),
            'link': row[4],
            'created': row[5]
        }
    return None

def save_pack(pack_type, pack_name, data):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    items_json = json.dumps(data.get('items', []))
    
    if pack_type == 'sticker':
        c.execute('''INSERT OR REPLACE INTO sticker_packs 
                     (pack_name, creator, items, published, link, created)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (pack_name, data['creator'], items_json, 
                   1 if data.get('published', False) else 0,
                   data.get('link', ''), data.get('created', datetime.now().isoformat())))
    else:
        c.execute('''INSERT OR REPLACE INTO emoji_packs 
                     (pack_name, creator, items, published, link, created)
                     VALUES (?, ?, ?, ?, ?, ?)''',
                  (pack_name, data['creator'], items_json,
                   1 if data.get('published', False) else 0,
                   data.get('link', ''), data.get('created', datetime.now().isoformat())))
    
    conn.commit()
    conn.close()

def delete_pack_db(pack_type, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    
    if pack_type == 'sticker':
        c.execute("DELETE FROM sticker_packs WHERE pack_name=?", (pack_name,))
    else:
        c.execute("DELETE FROM emoji_packs WHERE pack_name=?", (pack_name,))
    
    c.execute("DELETE FROM user_packs WHERE pack_name=?", (pack_name,))
    conn.commit()
    conn.close()

def get_user_packs(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT pack_type, pack_name FROM user_packs WHERE user_id=?", (user_id,))
    rows = c.fetchall()
    conn.close()
    
    packs = {'sticker': [], 'emoji': []}
    for pack_type, pack_name in rows:
        packs[pack_type].append(pack_name)
    return packs

def add_user_pack(user_id, pack_type, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO user_packs (user_id, pack_type, pack_name) VALUES (?, ?, ?)",
              (user_id, pack_type, pack_name))
    conn.commit()
    conn.close()

def remove_user_pack(user_id, pack_type, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM user_packs WHERE user_id=? AND pack_type=? AND pack_name=?",
              (user_id, pack_type, pack_name))
    conn.commit()
    conn.close()

# Initialize database
init_db()

# User states
user_states = {}
pending_packs = {}

# Main menu keyboard
def get_main_menu():
    keyboard = [
        [
            InlineKeyboardButton("📦 Create Sticker Pack", callback_data='create_sticker'),
            InlineKeyboardButton("🎨 Create Emoji Pack", callback_data='create_emoji')
        ],
        [
            InlineKeyboardButton("📋 My Packs", callback_data='my_packs'),
            InlineKeyboardButton("ℹ️ Help", callback_data='help')
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "👋 **Welcome to Sticker & Emoji Pack Bot!**\n\n"
            "✅ Sticker Pack - Photos, Videos, Stickers sab add ho jayenge\n"
            "✅ Emoji Pack - Photos, Videos, Stickers sab add ho jayenge\n\n"
            "Choose an option below:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )
    else:
        await update.message.reply_text(
            "👋 **Welcome to Sticker & Emoji Pack Bot!**\n\n"
            "✅ Sticker Pack - Photos, Videos, Stickers sab add ho jayenge\n"
            "✅ Emoji Pack - Photos, Videos, Stickers sab add ho jayenge\n\n"
            "Choose an option below:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data_callback = query.data
    
    if data_callback == 'create_sticker':
        await query.edit_message_text(
            "📦 **Create Sticker Pack**\n\n"
            "Send me the **name** for your sticker pack.\n"
            "Example: `MyCoolStickers`\n\n"
            "⚠️ No spaces (use underscores or camelCase)\n"
            "Type /cancel to cancel.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
        user_states[user_id] = 'awaiting_sticker_name'
    
    elif data_callback == 'create_emoji':
        await query.edit_message_text(
            "🎨 **Create Emoji Pack**\n\n"
            "Send me the **name** for your emoji pack.\n"
            "Example: `MyFunnyEmojis`\n\n"
            "⚠️ No spaces (use underscores or camelCase)\n"
            "Type /cancel to cancel.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
        user_states[user_id] = 'awaiting_emoji_name'
    
    elif data_callback == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif data_callback == 'help':
        await query.edit_message_text(
            "ℹ️ **How to use this bot:**\n\n"
            "1. Click 'Create Sticker Pack' or 'Create Emoji Pack'\n"
            "2. Send a name for your pack\n"
            "3. Send **photos**, **videos**, or **stickers** to add\n"
            "4. Type /publish to create the pack\n\n"
            "**✅ Sticker Pack:** Photos, Videos, Stickers all supported\n"
            "**✅ Emoji Pack:** Photos, Videos, Stickers all supported\n\n"
            "**⚠️ Note:** For real Telegram packs, register with @Stickers or @Emoji bot",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
    
    elif data_callback == 'back_to_main':
        await start(update, context)
    
    elif data_callback.startswith('view_pack_'):
        parts = data_callback.replace('view_pack_', '').split('_', 1)
        if len(parts) == 2:
            pack_type, pack_name = parts
            await view_pack(update, context, user_id, pack_type, pack_name)
    
    elif data_callback.startswith('add_to_pack_'):
        parts = data_callback.replace('add_to_pack_', '').split('_', 1)
        if len(parts) == 2:
            pack_type, pack_name = parts
            # Check if pack exists and belongs to user
            pack_data = get_pack(pack_type, pack_name)
            if not pack_data or pack_data['creator'] != user_id:
                await query.edit_message_text(
                    "❌ **Pack not found or you don't have permission!**\n\n"
                    "Make sure the pack exists and belongs to you.",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='my_packs')]])
                )
                return
            
            if user_id not in pending_packs:
                pending_packs[user_id] = {}
            pending_packs[user_id]['add_to'] = {'type': pack_type, 'name': pack_name}
            
            await query.edit_message_text(
                f"📤 **Adding to {pack_type.title()} Pack: {pack_name}**\n\n"
                "Send me a **photo**, **video**, or **sticker** to add.\n"
                "Type /cancel to cancel.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_type}_{pack_name}')]])
            )
    
    elif data_callback.startswith('delete_pack_'):
        parts = data_callback.replace('delete_pack_', '').split('_', 1)
        if len(parts) == 2:
            pack_type, pack_name = parts
            await delete_pack(update, context, user_id, pack_type, pack_name)
    
    elif data_callback.startswith('get_link_'):
        parts = data_callback.replace('get_link_', '').split('_', 1)
        if len(parts) == 2:
            pack_type, pack_name = parts
            await get_pack_link(update, context, user_id, pack_type, pack_name)
    
    elif data_callback.startswith('publish_pack_'):
        parts = data_callback.replace('publish_pack_', '').split('_', 1)
        if len(parts) == 2:
            pack_type, pack_name = parts
            await publish_pack(update, context, user_id, pack_type, pack_name)

async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None):
    if not user_id:
        user_id = str(update.effective_user.id)
    
    query = update.callback_query
    user_packs = get_user_packs(user_id)
    
    if not user_packs['sticker'] and not user_packs['emoji']:
        await query.edit_message_text(
            "📭 **You don't have any packs yet!**\n\n"
            "Click 'Create Sticker Pack' or 'Create Emoji Pack' to get started.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
        return
    
    keyboard = []
    
    if user_packs['sticker']:
        keyboard.append([InlineKeyboardButton("📦 Sticker Packs", callback_data='dummy')])
        for pack in user_packs['sticker']:
            keyboard.append([
                InlineKeyboardButton(f"📦 {pack}", callback_data=f'view_pack_sticker_{pack}')
            ])
    
    if user_packs['emoji']:
        keyboard.append([InlineKeyboardButton("🎨 Emoji Packs", callback_data='dummy')])
        for pack in user_packs['emoji']:
            keyboard.append([
                InlineKeyboardButton(f"🎨 {pack}", callback_data=f'view_pack_emoji_{pack}')
            ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_main')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "📋 **Your Packs**\n\n"
        "Select a pack to view or manage:",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
    query = update.callback_query
    
    pack_data = get_pack(pack_type, pack_name)
    
    if not pack_data or pack_data['creator'] != user_id:
        await query.edit_message_text(
            "❌ **Pack not found or you don't have permission!**\n\n"
            "Make sure the pack exists and belongs to you.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to My Packs", callback_data='my_packs')]
            ])
        )
        return
    
    items = pack_data.get('items', [])
    items_count = len(items)
    pack_link = pack_data.get('link', 'Not created yet')
    is_published = pack_data.get('published', False)
    
    # Show preview of items
    preview = ""
    if items_count > 0:
        preview = f"\n\n📸 **Items:** {items_count}"
        types = {}
        for item in items:
            item_type = item.get('type', 'unknown')
            types[item_type] = types.get(item_type, 0) + 1
        if types:
            preview += "\n" + ", ".join([f"{t}: {c}" for t, c in types.items()])
    
    keyboard = [
        [InlineKeyboardButton("📤 Add Item", callback_data=f'add_to_pack_{pack_type}_{pack_name}')]
    ]
    
    if not is_published and items_count > 0:
        keyboard.append([InlineKeyboardButton("🚀 Publish Pack", callback_data=f'publish_pack_{pack_type}_{pack_name}')])
    
    keyboard.append([InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_type}_{pack_name}')])
    keyboard.append([InlineKeyboardButton("🗑️ Delete Pack", callback_data=f'delete_pack_{pack_type}_{pack_name}')])
    keyboard.append([InlineKeyboardButton("🔙 Back to My Packs", callback_data='my_packs')])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    status = "✅ Published" if is_published else "⏳ Draft"
    
    await query.edit_message_text(
        f"📦 **{pack_type.title()} Pack: {pack_name}**\n\n"
        f"📊 Status: {status}\n"
        f"📊 Total Items: {items_count}\n"
        f"🔗 Link: `{pack_link}`{preview}\n\n"
        f"What would you like to do?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

async def get_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
    query = update.callback_query
    
    pack_data = get_pack(pack_type, pack_name)
    
    if not pack_data or pack_data['creator'] != user_id:
        await query.edit_message_text(
            "❌ Pack not found!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='my_packs')]])
        )
        return
    
    is_published = pack_data.get('published', False)
    items_count = len(pack_data.get('items', []))
    
    if pack_type == 'sticker':
        real_link = f"https://t.me/addstickers/{pack_name}"
    else:
        real_link = f"https://t.me/addemoji/{pack_name}"
    
    if is_published:
        link_msg = f"✅ **Pack is Published!**\n\n🔗 **Link:** `{real_link}`\n\nClick the link to add this pack to Telegram!"
    else:
        link_msg = (
            f"⏳ **Pack is not published yet!**\n\n"
            f"📦 Pack Name: `{pack_name}`\n"
            f"📊 Items: {items_count}\n\n"
            f"**To publish:**\n"
            f"1. Add at least 1 item\n"
            f"2. Go back and click 'Publish Pack'\n\n"
            f"**Note:** After publishing, use this link:\n`{real_link}`"
        )
    
    await query.edit_message_text(
        link_msg,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Pack", callback_data=f'view_pack_{pack_type}_{pack_name}')],
            [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')]
        ])
    )

async def delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
    query = update.callback_query
    
    # Verify pack belongs to user
    pack_data = get_pack(pack_type, pack_name)
    if not pack_data or pack_data['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!")
        return
    
    delete_pack_db(pack_type, pack_name)
    remove_user_pack(user_id, pack_type, pack_name)
    
    await query.edit_message_text(
        f"✅ **Pack '{pack_name}' deleted successfully!**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to My Packs", callback_data='my_packs')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
        ])
    )

async def publish_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
    query = update.callback_query
    
    pack_data = get_pack(pack_type, pack_name)
    
    if not pack_data or pack_data['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!")
        return
    
    items = pack_data.get('items', [])
    
    if not items:
        await query.edit_message_text(
            "❌ **Cannot publish empty pack!**\n\n"
            "Add at least 1 item first.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_type}_{pack_name}')]])
        )
        return
    
    try:
        # Get first item
        first_item = items[0]
        file_id = first_item.get('file_id')
        
        file_info = await context.bot.get_file(file_id)
        file_content = await file_info.download_as_bytearray()
        
        # Determine sticker type
        item_type = first_item.get('type', 'photo')
        if item_type == 'sticker':
            sticker_type = 'webp_sticker'
        elif item_type == 'video':
            sticker_type = 'webm_sticker'
        else:
            sticker_type = 'png_sticker'
        
        # Create sticker pack
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
        params = {
            'user_id': int(user_id),
            'name': pack_name,
            'title': pack_name.replace('_', ' ').title(),
            'emojis': '😀'
        }
        files = {sticker_type: ('sticker', file_content)}
        response = requests.post(api_url, data=params, files=files)
        result = response.json()
        
        if not result.get('ok'):
            if 'name is already occupied' in str(result):
                pack_data['published'] = True
                save_pack(pack_type, pack_name, pack_data)
                await query.edit_message_text(
                    f"✅ **Pack already exists!**\n\n"
                    f"🔗 Link: `https://t.me/addstickers/{pack_name}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_type}_{pack_name}')]])
                )
                return
            else:
                await query.edit_message_text(
                    f"❌ **Error:** {result}\n\n"
                    f"⚠️ Make sure pack name is unique and valid.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        # Add remaining items
        for item in items[1:]:
            file_id = item.get('file_id')
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            item_type = item.get('type', 'photo')
            if item_type == 'sticker':
                add_sticker_type = 'webp_sticker'
            elif item_type == 'video':
                add_sticker_type = 'webm_sticker'
            else:
                add_sticker_type = 'png_sticker'
            
            add_url = f"https://api.telegram.org/bot{TOKEN}/addStickerToSet"
            add_params = {
                'user_id': int(user_id),
                'name': pack_name,
                'emojis': '😀'
            }
            add_files = {add_sticker_type: ('sticker', file_content)}
            requests.post(add_url, data=add_params, files=add_files)
        
        # Update pack data
        pack_data['published'] = True
        pack_data['link'] = f"https://t.me/addstickers/{pack_name}"
        save_pack(pack_type, pack_name, pack_data)
        
        await query.edit_message_text(
            f"✅ **Pack published successfully!**\n\n"
            f"📦 **Pack:** {pack_name}\n"
            f"🔗 **Link:** `https://t.me/addstickers/{pack_name}`\n"
            f"📊 **Items:** {len(items)}\n\n"
            f"Click the link to add this pack to Telegram!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_type}_{pack_name}')]])
        )
        
    except Exception as e:
        logger.error(f"Error publishing pack: {e}")
        await query.edit_message_text(
            f"❌ **Error publishing pack:** {str(e)}\n\n"
            f"Try using @Stickers bot directly.",
            parse_mode=ParseMode.MARKDOWN
        )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    # Check if user is creating a pack
    if user_id in user_states:
        state = user_states[user_id]
        
        if state == 'awaiting_sticker_name':
            pack_name = message.text.strip().replace(' ', '_')
            if not pack_name:
                await message.reply_text("❌ Please send a valid name!")
                return
            
            # Check if pack exists
            existing = get_pack('sticker', pack_name)
            if existing:
                await message.reply_text("❌ A sticker pack with this name already exists!")
                return
            
            # Create sticker pack
            pack_data = {
                'creator': user_id,
                'items': [],
                'published': False,
                'link': f"https://t.me/addstickers/{pack_name}",
                'created': datetime.now().isoformat()
            }
            save_pack('sticker', pack_name, pack_data)
            add_user_pack(user_id, 'sticker', pack_name)
            
            del user_states[user_id]
            
            await message.reply_text(
                f"✅ **Sticker pack '{pack_name}' created!**\n\n"
                f"📤 Send me **photos**, **videos**, or **stickers** to add.\n"
                f"Type /publish when done.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_sticker_{pack_name}')],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
                ])
            )
            return
        
        elif state == 'awaiting_emoji_name':
            pack_name = message.text.strip().replace(' ', '_')
            if not pack_name:
                await message.reply_text("❌ Please send a valid name!")
                return
            
            # Check if pack exists
            existing = get_pack('emoji', pack_name)
            if existing:
                await message.reply_text("❌ An emoji pack with this name already exists!")
                return
            
            # Create emoji pack
            pack_data = {
                'creator': user_id,
                'items': [],
                'published': False,
                'link': f"https://t.me/addemoji/{pack_name}",
                'created': datetime.now().isoformat()
            }
            save_pack('emoji', pack_name, pack_data)
            add_user_pack(user_id, 'emoji', pack_name)
            
            del user_states[user_id]
            
            await message.reply_text(
                f"✅ **Emoji pack '{pack_name}' created!**\n\n"
                f"📤 Send me **photos**, **videos**, or **stickers** to add.\n"
                f"Type /publish when done.",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_emoji_{pack_name}')],
                    [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
                ])
            )
            return
    
    # Check if user is adding to existing pack
    if user_id in pending_packs and 'add_to' in pending_packs[user_id]:
        add_info = pending_packs[user_id]['add_to']
        pack_type = add_info['type']
        pack_name = add_info['name']
        
        pack_data = get_pack(pack_type, pack_name)
        
        if not pack_data or pack_data['creator'] != user_id:
            await message.reply_text("❌ Pack not found!")
            del pending_packs[user_id]
            return
        
        # Handle different media types
        file_id = None
        item_type = None
        
        if message.photo:
            file_id = message.photo[-1].file_id
            item_type = 'photo'
        elif message.video:
            file_id = message.video.file_id
            item_type = 'video'
        elif message.sticker:
            file_id = message.sticker.file_id
            item_type = 'sticker'
        elif message.document:
            doc = message.document
            if doc.mime_type in ['image/png', 'image/webp', 'video/mp4']:
                file_id = doc.file_id
                if doc.mime_type == 'video/mp4':
                    item_type = 'video'
                else:
                    item_type = 'photo'
            else:
                await message.reply_text("❌ Please send a photo, video, or sticker!")
                return
        else:
            await message.reply_text(
                "❌ **Please send a photo, video, or sticker!**",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        # Add item to pack
        items = pack_data.get('items', [])
        items.append({'type': item_type, 'file_id': file_id})
        pack_data['items'] = items
        save_pack(pack_type, pack_name, pack_data)
        
        await message.reply_text(
            f"✅ **Item added to {pack_type.title()} Pack!**\n\n"
            f"📊 Total items: {len(items)}\n"
            f"📤 Send more items or type /publish to create the pack.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_type}_{pack_name}')],
                [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
            ])
        )
        return
    
    # If no state, show main menu
    await message.reply_text(
        "Use /start to begin!",
        reply_markup=get_main_menu()
    )

async def publish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    user_packs = get_user_packs(user_id)
    
    found_pack = None
    found_type = None
    
    # Check sticker packs
    for pack_name in user_packs.get('sticker', []):
        pack_data = get_pack('sticker', pack_name)
        if pack_data and not pack_data.get('published', False) and len(pack_data.get('items', [])) > 0:
            found_pack = pack_name
            found_type = 'sticker'
            break
    
    # Check emoji packs
    if not found_pack:
        for pack_name in user_packs.get('emoji', []):
            pack_data = get_pack('emoji', pack_name)
            if pack_data and not pack_data.get('published', False) and len(pack_data.get('items', [])) > 0:
                found_pack = pack_name
                found_type = 'emoji'
                break
    
    if not found_pack:
        await message.reply_text(
            "❌ **No unpublished packs with items found!**\n\n"
            "Create a pack and add items first.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )
        return
    
    await publish_specific_pack(update, context, user_id, found_type, found_pack)

async def publish_specific_pack(update, context, user_id, pack_type, pack_name):
    pack_data = get_pack(pack_type, pack_name)
    
    if not pack_data:
        await update.message.reply_text("❌ Pack not found!")
        return
    
    items = pack_data.get('items', [])
    
    if not items:
        await update.message.reply_text("❌ Cannot publish empty pack!")
        return
    
    try:
        # Get first item
        first_item = items[0]
        file_id = first_item.get('file_id')
        
        file_info = await context.bot.get_file(file_id)
        file_content = await file_info.download_as_bytearray()
        
        # Determine sticker type
        item_type = first_item.get('type', 'photo')
        if item_type == 'sticker':
            sticker_type = 'webp_sticker'
        elif item_type == 'video':
            sticker_type = 'webm_sticker'
        else:
            sticker_type = 'png_sticker'
        
        # Create sticker pack
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
        params = {
            'user_id': int(user_id),
            'name': pack_name,
            'title': pack_name.replace('_', ' ').title(),
            'emojis': '😀'
        }
        files = {sticker_type: ('sticker', file_content)}
        response = requests.post(api_url, data=params, files=files)
        result = response.json()
        
        if not result.get('ok'):
            if 'name is already occupied' in str(result):
                pack_data['published'] = True
                save_pack(pack_type, pack_name, pack_data)
                await update.message.reply_text(
                    f"✅ **Pack already exists!**\n\n"
                    f"🔗 Link: `https://t.me/addstickers/{pack_name}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=get_main_menu()
                )
                return
            else:
                await update.message.reply_text(
                    f"❌ **Error:** {result}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        # Add remaining items
        for item in items[1:]:
            file_id = item.get('file_id')
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            item_type = item.get('type', 'photo')
            if item_type == 'sticker':
                add_sticker_type = 'webp_sticker'
            elif item_type == 'video':
                add_sticker_type = 'webm_sticker'
            else:
                add_sticker_type = 'png_sticker'
            
            add_url = f"https://api.telegram.org/bot{TOKEN}/addStickerToSet"
            add_params = {
                'user_id': int(user_id),
                'name': pack_name,
                'emojis': '😀'
            }
            add_files = {add_sticker_type: ('sticker', file_content)}
            requests.post(add_url, data=add_params, files=add_files)
        
        # Update pack data
        pack_data['published'] = True
        pack_data['link'] = f"https://t.me/addstickers/{pack_name}"
        save_pack(pack_type, pack_name, pack_data)
        
        await update.message.reply_text(
            f"✅ **Pack published successfully!**\n\n"
            f"📦 **Pack:** {pack_name}\n"
            f"🔗 **Link:** `https://t.me/addstickers/{pack_name}`\n"
            f"📊 **Items:** {len(items)}\n\n"
            f"Click the link to add this pack to Telegram!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )
        
    except Exception as e:
        logger.error(f"Error publishing pack: {e}")
        await update.message.reply_text(
            f"❌ **Error publishing pack:** {str(e)}",
            parse_mode=ParseMode.MARKDOWN
        )

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
    if user_id in pending_packs:
        del pending_packs[user_id]
    await update.message.reply_text(
        "❌ **Process cancelled!**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=get_main_menu()
    )

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ **An error occurred!** Please try again.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=get_main_menu()
        )

def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CommandHandler("publish", publish))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.Sticker.ALL | filters.Document.ALL, 
        handle_message
    ))
    application.add_error_handler(error_handler)
    
    print("🤖 Bot is starting...")
    print(f"📊 Database: {DATABASE}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
