import os
import json
import logging
import sqlite3
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
DATABASE = 'packs.db'

# ============ DATABASE ============
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS packs
                 (pack_name TEXT PRIMARY KEY, 
                  creator TEXT, 
                  items TEXT, 
                  published INTEGER, 
                  link TEXT, 
                  created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_packs
                 (user_id TEXT, pack_name TEXT,
                  PRIMARY KEY (user_id, pack_name))''')
    conn.commit()
    conn.close()

def get_pack(pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT * FROM packs WHERE pack_name=?", (pack_name,))
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

def save_pack(pack_name, data):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    items_json = json.dumps(data.get('items', []))
    c.execute('''INSERT OR REPLACE INTO packs 
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
    c.execute("DELETE FROM packs WHERE pack_name=?", (pack_name,))
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
    c.execute("INSERT OR IGNORE INTO user_packs (user_id, pack_name) VALUES (?, ?)", (user_id, pack_name))
    conn.commit()
    conn.close()

def remove_user_pack(user_id, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM user_packs WHERE user_id=? AND pack_name=?", (user_id, pack_name))
    conn.commit()
    conn.close()

init_db()

# ============ USER STATES ============
user_steps = {}  # Stores current step for each user
user_data = {}   # Stores temporary data

# ============ KEYBOARDS ============
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Create Sticker Pack", callback_data='create_pack')],
        [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

def back_button():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')]])

# ============ START ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username
    
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            f"👋 **Welcome!**\n\n"
            f"I will help you create Sticker Packs easily.\n\n"
            f"📌 **Your Bot Username:** @{bot_username}\n"
            f"📌 **Pack name must end with:** `_by_{bot_username}`\n\n"
            f"Click below to start!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu()
        )
    else:
        await update.message.reply_text(
            f"👋 **Welcome!**\n\n"
            f"I will help you create Sticker Packs easily.\n\n"
            f"📌 **Your Bot Username:** @{bot_username}\n"
            f"📌 **Pack name must end with:** `_by_{bot_username}`\n\n"
            f"Click below to start!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu()
        )

# ============ BUTTON HANDLER ============
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == 'create_pack':
        bot_username = context.bot.username
        await query.edit_message_text(
            f"📦 **Step 1: Give your pack a name**\n\n"
            f"Send me a name for your sticker pack.\n\n"
            f"⚠️ **Important:** Name must end with `_by_{bot_username}`\n\n"
            f"📝 **Example:** `my_stickers_by_{bot_username}`\n\n"
            f"Type /cancel to cancel.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=back_button()
        )
        user_steps[user_id] = 'waiting_for_name'
    
    elif query.data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif query.data == 'help':
        await query.edit_message_text(
            "ℹ️ **How to create a sticker pack:**\n\n"
            "1️⃣ Click 'Create Sticker Pack'\n"
            "2️⃣ Send a pack name (must end with _by_botusername)\n"
            "3️⃣ Send PNG images as documents\n"
            "4️⃣ Click 'Publish Pack' to create it!\n\n"
            "📌 **First sticker MUST be PNG format!**\n"
            "📌 PNG must be 512x512 pixels\n"
            "📌 Max 512KB per sticker",
            reply_markup=main_menu()
        )
    
    elif query.data == 'back_to_menu':
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
    
    elif query.data.startswith('publish_pack_'):
        pack_name = query.data.replace('publish_pack_', '')
        await publish_pack(update, context, user_id, pack_name)

# ============ SHOW MY PACKS ============
async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None):
    if not user_id:
        user_id = str(update.effective_user.id)
    
    query = update.callback_query
    packs = get_user_packs(user_id)
    
    if not packs:
        await query.edit_message_text(
            "📭 **You don't have any packs yet!**\n\nClick 'Create Sticker Pack' to start.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu()
        )
        return
    
    keyboard = []
    for pack in packs:
        pack_data = get_pack(pack)
        if pack_data:
            status = "✅" if pack_data.get('published') else "⏳"
            keyboard.append([InlineKeyboardButton(f"{status} {pack}", callback_data=f'view_pack_{pack}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back to Menu", callback_data='back_to_menu')])
    
    await query.edit_message_text(
        "📋 **Your Packs:**\n\n✅ = Published | ⏳ = Draft",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============ VIEW PACK ============
async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text(
            "❌ Pack not found!",
            reply_markup=main_menu()
        )
        return
    
    items = pack.get('items', [])
    published = pack.get('published', False)
    link = pack.get('link', 'Not created yet')
    
    status = "✅ Published" if published else "⏳ Draft"
    item_count = len(items)
    
    keyboard = []
    
    if not published:
        keyboard.append([InlineKeyboardButton("📤 Add Sticker", callback_data=f'add_to_pack_{pack_name}')])
        if item_count > 0:
            keyboard.append([InlineKeyboardButton("🚀 Publish Pack", callback_data=f'publish_pack_{pack_name}')])
    else:
        keyboard.append([InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')])
    
    keyboard.append([InlineKeyboardButton("🗑️ Delete Pack", callback_data=f'delete_pack_{pack_name}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_packs')])
    
    await query.edit_message_text(
        f"📦 **Pack: {pack_name}**\n\n"
        f"📊 Status: {status}\n"
        f"📸 Stickers: {item_count}\n"
        f"🔗 Link: `{link}`\n\n"
        f"What would you like to do?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ============ GET LINK ============
async def get_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    link = f"https://t.me/addstickers/{pack_name}"
    
    await query.edit_message_text(
        f"🔗 **Your Pack Link:**\n\n"
        f"`{link}`\n\n"
        f"📌 Click the link to add this pack to Telegram!\n"
        f"📊 Total stickers: {len(pack.get('items', []))}",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Pack", callback_data=f'view_pack_{pack_name}')],
            [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')]
        ])
    )

# ============ DELETE PACK ============
async def delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    delete_pack_db(pack_name)
    remove_user_pack(user_id, pack_name)
    
    await query.edit_message_text(
        f"✅ **Pack '{pack_name}' deleted successfully!**",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )

# ============ ADD TO PACK ============
async def add_to_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    
    # Store which pack user is adding to
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['adding_to'] = pack_name
    
    await query.edit_message_text(
        f"📤 **Step 2: Send your sticker**\n\n"
        f"Send a **PNG image** as a document.\n\n"
        f"📌 PNG must be 512x512 pixels\n"
        f"📌 Max 512KB file size\n\n"
        f"Send multiple stickers one by one.\n"
        f"Type /done when finished.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Pack", callback_data=f'view_pack_{pack_name}')]
        ])
    )
    
    # Update step
    user_steps[user_id] = 'waiting_for_sticker'

# ============ PUBLISH PACK ============
async def publish_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    items = pack.get('items', [])
    
    if not items:
        await query.edit_message_text(
            "❌ **Cannot publish empty pack!**\n\n"
            "Add at least 1 sticker first.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
        )
        return
    
    await query.edit_message_text(
        "⏳ **Publishing your pack...**\n\n"
        "This may take a few seconds.",
        parse_mode=ParseMode.MARKDOWN
    )
    
    try:
        # Get first sticker
        first_item = items[0]
        file_id = first_item.get('file_id')
        file_info = await context.bot.get_file(file_id)
        file_content = await file_info.download_as_bytearray()
        
        # Create pack
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
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
                pack['published'] = True
                save_pack(pack_name, pack)
                await query.edit_message_text(
                    f"✅ **Pack already exists!**\n\n"
                    f"🔗 `https://t.me/addstickers/{pack_name}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
                )
                return
            else:
                await query.edit_message_text(
                    f"❌ **Error:** {error_msg}",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        # Add remaining stickers
        for item in items[1:]:
            file_id = item.get('file_id')
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            add_url = f"https://api.telegram.org/bot{TOKEN}/addStickerToSet"
            add_params = {
                'user_id': int(user_id),
                'name': pack_name,
                'emojis': '😀'
            }
            add_files = {'png_sticker': ('sticker.png', file_content)}
            requests.post(add_url, data=add_params, files=add_files)
        
        # Update pack
        pack['published'] = True
        save_pack(pack_name, pack)
        
        link = f"https://t.me/addstickers/{pack_name}"
        
        await query.edit_message_text(
            f"✅ **Pack published successfully!**\n\n"
            f"📦 **Name:** {pack_name}\n"
            f"📊 **Stickers:** {len(items)}\n"
            f"🔗 **Link:** `{link}`\n\n"
            f"🎉 Click the link to add this pack to Telegram!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')],
                [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

# ============ HANDLE MESSAGES ============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    # Step 1: Waiting for pack name
    if user_id in user_steps and user_steps[user_id] == 'waiting_for_name':
        pack_name = message.text.strip().replace(' ', '_')
        bot_username = context.bot.username
        expected_suffix = f"_by_{bot_username}"
        
        if not pack_name.endswith(expected_suffix):
            await message.reply_text(
                f"❌ **Wrong format!**\n\n"
                f"Name must end with `{expected_suffix}`\n\n"
                f"📝 Example: `my_stickers{expected_suffix}`\n\n"
                f"Try again or type /cancel",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if get_pack(pack_name):
            await message.reply_text(
                "❌ **This name is already taken!**\n\n"
                "Please choose another name."
            )
            return
        
        # Create pack
        data = {
            'creator': user_id,
            'items': [],
            'published': False,
            'link': f"https://t.me/addstickers/{pack_name}",
            'created': datetime.now().isoformat()
        }
        save_pack(pack_name, data)
        add_user_pack(user_id, pack_name)
        
        # Store pack name for adding stickers
        if user_id not in user_data:
            user_data[user_id] = {}
        user_data[user_id]['current_pack'] = pack_name
        
        # Change state
        user_steps[user_id] = 'waiting_for_sticker'
        
        await message.reply_text(
            f"✅ **Pack '{pack_name}' created!**\n\n"
            f"📤 **Step 2: Send your stickers**\n\n"
            f"Send **PNG images** as documents.\n"
            f"📌 512x512 pixels, max 512KB\n\n"
            f"Send multiple stickers one by one.\n"
            f"Type /done when finished.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')]
            ])
        )
        return
    
    # Step 2: Waiting for stickers
    elif user_id in user_steps and user_steps[user_id] == 'waiting_for_sticker':
        # Check if user has a pack
        pack_name = user_data.get(user_id, {}).get('current_pack')
        
        if not pack_name:
            await message.reply_text(
                "❌ No pack found! Use /start to create one."
            )
            return
        
        # Handle document
        if message.document:
            doc = message.document
            if doc.mime_type == 'image/png':
                pack = get_pack(pack_name)
                if not pack or pack['creator'] != user_id:
                    await message.reply_text("❌ Pack not found!")
                    return
                
                # Add sticker
                items = pack.get('items', [])
                items.append({'type': 'png_sticker', 'file_id': doc.file_id})
                pack['items'] = items
                save_pack(pack_name, pack)
                
                await message.reply_text(
                    f"✅ **Sticker added!** ({len(items)} total)\n\n"
                    f"Send more or type /done to finish."
                )
            else:
                await message.reply_text(
                    "❌ **Only PNG images are supported!**\n\n"
                    "Send a PNG file as a document."
                )
        else:
            await message.reply_text(
                "❌ **Send a PNG file as a document!**\n\n"
                "Use the 📎 attachment button and select 'File'."
            )
        return
    
    # /done command handler
    elif message.text and message.text.lower() == '/done':
        await done(update, context)
        return
    
    # Default
    await message.reply_text(
        "Use /start to create a sticker pack!",
        reply_markup=main_menu()
    )

# ============ DONE COMMAND ============
async def done(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
    pack_name = user_data.get(user_id, {}).get('current_pack')
    
    if not pack_name:
        await update.message.reply_text("❌ No pack in progress!")
        return
    
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await update.message.reply_text("❌ Pack not found!")
        return
    
    items = pack.get('items', [])
    
    if not items:
        await update.message.reply_text(
            "❌ **No stickers added!**\n\n"
            "Send at least 1 PNG image first."
        )
        return
    
    # Show summary
    await update.message.reply_text(
        f"📦 **Pack Summary:**\n\n"
        f"📦 Name: {pack_name}\n"
        f"📸 Stickers: {len(items)}\n\n"
        f"What would you like to do?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Publish Pack", callback_data=f'publish_pack_{pack_name}')],
            [InlineKeyboardButton("📤 Add More", callback_data=f'add_to_pack_{pack_name}')],
            [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')]
        ])
    )

# ============ CANCEL ============
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_steps:
        del user_steps[user_id]
    if user_id in user_data:
        del user_data[user_id]
    await update.message.reply_text(
        "❌ **Cancelled!**\n\nUse /start to begin again.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu()
    )

# ============ MAIN ============
def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel))
    app.add_handler(CommandHandler("done", done))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_message))
    
    print("🤖 Bot is starting...")
    app.run_polling()

if __name__ == '__main__':
    main()
