import os
import sys
import json
import logging
import sqlite3
import requests
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageOps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

# ============ LOGGING ============
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============ TOKEN (Hardcoded) ============
TOKEN = "8799309309:AAEy_csS6ESN8NObQlxHMss5YPmYEGOEtcc"

# Verify token format
if not TOKEN or len(TOKEN) < 30:
    logger.error("❌ Invalid token format!")
    sys.exit(1)

logger.info(f"✅ Bot token loaded: {TOKEN[:10]}...")

# ============ DATABASE ============
DATABASE = 'packs.db'
TEMP_DIR = 'temp'

# Create temp directory
os.makedirs(TEMP_DIR, exist_ok=True)

def init_db():
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS packs
                     (pack_name TEXT PRIMARY KEY, creator TEXT, items TEXT, 
                      published INTEGER, link TEXT, created TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_packs
                     (user_id TEXT, pack_name TEXT, PRIMARY KEY (user_id, pack_name))''')
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"❌ Database error: {e}")

def get_pack(pack_name):
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT * FROM packs WHERE pack_name=?", (pack_name,))
        row = c.fetchone()
        conn.close()
        if row:
            return {'pack_name': row[0], 'creator': row[1], 
                    'items': json.loads(row[2]) if row[2] else [],
                    'published': bool(row[3]), 'link': row[4], 'created': row[5]}
        return None
    except Exception as e:
        logger.error(f"Error getting pack: {e}")
        return None

def save_pack(pack_name, data):
    try:
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
        return True
    except Exception as e:
        logger.error(f"Error saving pack: {e}")
        return False

def delete_pack_db(pack_name):
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("DELETE FROM packs WHERE pack_name=?", (pack_name,))
        c.execute("DELETE FROM user_packs WHERE pack_name=?", (pack_name,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error deleting pack: {e}")
        return False

def get_user_packs(user_id):
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("SELECT pack_name FROM user_packs WHERE user_id=?", (user_id,))
        rows = c.fetchall()
        conn.close()
        return [row[0] for row in rows]
    except Exception as e:
        logger.error(f"Error getting user packs: {e}")
        return []

def add_user_pack(user_id, pack_name):
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO user_packs (user_id, pack_name) VALUES (?, ?)", (user_id, pack_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error adding user pack: {e}")
        return False

def remove_user_pack(user_id, pack_name):
    try:
        conn = sqlite3.connect(DATABASE)
        c = conn.cursor()
        c.execute("DELETE FROM user_packs WHERE user_id=? AND pack_name=?", (user_id, pack_name))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"Error removing user pack: {e}")
        return False

init_db()

# ============ IMAGE CONVERTER ============
def convert_to_png(file_content, file_type):
    """Convert any media to PNG format"""
    try:
        if file_type == 'photo':
            image = Image.open(BytesIO(file_content))
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            image = ImageOps.fit(image, (512, 512), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
        
        elif file_type == 'sticker':
            image = Image.open(BytesIO(file_content))
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            image = ImageOps.fit(image, (512, 512), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format='PNG')
            return output.getvalue()
        
        elif file_type == 'video':
            try:
                image = Image.open(BytesIO(file_content))
                if image.mode in ('RGBA', 'LA', 'P'):
                    image = image.convert('RGB')
                image = ImageOps.fit(image, (512, 512), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format='PNG')
                return output.getvalue()
            except:
                img = Image.new('RGB', (512, 512), color=(50, 50, 80))
                output = BytesIO()
                img.save(output, format='PNG')
                return output.getvalue()
        
        else:
            raise Exception(f"Unsupported file type: {file_type}")
            
    except Exception as e:
        logger.error(f"Conversion error: {e}")
        raise e

# ============ USER STATES ============
user_steps = {}
user_data = {}

# ============ KEYBOARDS ============
def main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Create Sticker Pack", callback_data='create_pack')],
        [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

# ============ START ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username
    msg = f"""👋 **Welcome to Sticker Pack Bot!**

✅ **Auto Convert Feature:**
📸 Photo → PNG (512x512)
🎬 Video → PNG (Thumbnail)
🏷️ Sticker → PNG (512x512)

📌 **Pack name must end with:** `_by_{bot_username}`

Click below to start!"""

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())

# ============ BUTTON HANDLER ============
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == 'create_pack':
        bot_username = context.bot.username
        await query.edit_message_text(
            f"📦 **Step 1: Pack Name**\n\n"
            f"Send pack name like this:\n"
            f"`my_pack_by_{bot_username}`\n\n"
            f"⚠️ Must end with `_by_{bot_username}`\n"
            f"Type /cancel to cancel",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]])
        )
        user_steps[user_id] = 'waiting_for_name'
    
    elif query.data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif query.data == 'help':
        await query.edit_message_text(
            "ℹ️ **How to create a sticker pack:**\n\n"
            "1️⃣ Click 'Create Sticker Pack'\n"
            "2️⃣ Send pack name (must end with _by_botusername)\n"
            "3️⃣ Send **photo**, **video**, or **sticker**\n"
            "4️⃣ Bot auto-converts to PNG\n"
            "5️⃣ Type /done when finished\n"
            "6️⃣ Click 'Publish Pack'\n\n"
            "✅ All media auto-converted to PNG!",
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
async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    query = update.callback_query
    packs = get_user_packs(user_id)
    
    if not packs:
        await query.edit_message_text("📭 No packs yet!", reply_markup=main_menu())
        return
    
    keyboard = []
    for pack in packs:
        pack_data = get_pack(pack)
        if pack_data:
            status = "✅" if pack_data.get('published') else "⏳"
            keyboard.append([InlineKeyboardButton(f"{status} {pack}", callback_data=f'view_pack_{pack}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')])
    await query.edit_message_text("📋 Your Packs:", reply_markup=InlineKeyboardMarkup(keyboard))

# ============ VIEW PACK ============
async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    items = pack.get('items', [])
    published = pack.get('published', False)
    
    keyboard = []
    if not published:
        keyboard.append([InlineKeyboardButton("📤 Add Media", callback_data=f'add_to_pack_{pack_name}')])
        if len(items) > 0:
            keyboard.append([InlineKeyboardButton("🚀 Publish Pack", callback_data=f'publish_pack_{pack_name}')])
    else:
        keyboard.append([InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')])
    
    keyboard.append([InlineKeyboardButton("🗑️ Delete Pack", callback_data=f'delete_pack_{pack_name}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_packs')])
    
    status = "✅ Published" if published else "⏳ Draft"
    await query.edit_message_text(
        f"📦 **{pack_name}**\n\n"
        f"Status: {status}\n"
        f"Items: {len(items)}\n\n"
        f"✅ Photo/Video/Sticker → PNG auto converted!",
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
        f"🔗 **Your Pack Link:**\n\n`{link}`\n\n✅ Click to add to Telegram!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]
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
    await query.edit_message_text("✅ Deleted!", reply_markup=main_menu())

# ============ PUBLISH PACK ============
async def publish_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    
    pack = get_pack(pack_name)
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    items = pack.get('items', [])
    if not items:
        await query.edit_message_text("❌ Add at least 1 item!", 
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]]))
        return
    
    await query.edit_message_text("⏳ Publishing... Please wait...")
    
    try:
        # Get first item (already converted to PNG)
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
                    f"✅ Pack already exists!\n\n🔗 `https://t.me/addstickers/{pack_name}`",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
                )
                return
            else:
                await query.edit_message_text(f"❌ Error: {error_msg}")
                return
        
        # Add remaining items (all already PNG)
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
            f"✅ **Pack Published!**\n\n"
            f"📦 {pack_name}\n"
            f"📊 {len(items)} items\n"
            f"🔗 `{link}`\n\n"
            f"🎉 Click link to add to Telegram!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')],
                [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await query.edit_message_text(f"❌ Error: {str(e)}")

# ============ ADD TO PACK ============
async def add_to_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['current_pack'] = pack_name
    user_steps[user_id] = 'waiting_for_media'
    
    await query.edit_message_text(
        f"📤 **Send Photo, Video, or Sticker**\n\n"
        f"Bot will auto-convert to PNG (512x512)\n\n"
        f"✅ Photo → PNG\n"
        f"✅ Video → PNG (Thumbnail)\n"
        f"✅ Sticker → PNG\n\n"
        f"Type /done when finished.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
    )

# ============ HANDLE MESSAGES ============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    # /done command
    if message.text and message.text.lower() == '/done':
        await done(update, context)
        return
    
    # Step 1: Waiting for name
    if user_id in user_steps and user_steps[user_id] == 'waiting_for_name':
        pack_name = message.text.strip().replace(' ', '_')
        bot_username = context.bot.username
        expected_suffix = f"_by_{bot_username}"
        
        if not pack_name.endswith(expected_suffix):
            await message.reply_text(
                f"❌ Name must end with `{expected_suffix}`\n\n"
                f"Example: `my_pack{expected_suffix}`",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        
        if get_pack(pack_name):
            await message.reply_text("❌ Name already taken!")
            return
        
        # Create pack
        data = {'creator': user_id, 'items': [], 'published': False,
                'link': f"https://t.me/addstickers/{pack_name}",
                'created': datetime.now().isoformat()}
        save_pack(pack_name, data)
        add_user_pack(user_id, pack_name)
        
        user_data[user_id] = {'current_pack': pack_name}
        user_steps[user_id] = 'waiting_for_media'
        
        await message.reply_text(
            f"✅ Pack '{pack_name}' created!\n\n"
            "📤 Send **photo**, **video**, or **sticker**\n"
            "Bot will auto-convert to PNG!\n"
            "Type /done when finished.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')]])
        )
        return
    
    # Step 2: Waiting for media
    if user_id in user_steps and user_steps[user_id] == 'waiting_for_media':
        pack_name = user_data.get(user_id, {}).get('current_pack')
        if not pack_name:
            await message.reply_text("❌ No pack found!")
            return
        
        pack = get_pack(pack_name)
        if not pack:
            await message.reply_text("❌ Pack not found!")
            return
        
        # Detect media type
        file_id = None
        media_type = None
        
        if message.photo:
            file_id = message.photo[-1].file_id
            media_type = 'photo'
        elif message.video:
            file_id = message.video.file_id
            media_type = 'video'
        elif message.sticker:
            file_id = message.sticker.file_id
            media_type = 'sticker'
        else:
            await message.reply_text("❌ Send Photo, Video, or Sticker!")
            return
        
        # Download and convert to PNG
        try:
            await message.reply_text("🔄 Converting to PNG...")
            
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            # Convert to PNG
            png_content = convert_to_png(file_content, media_type)
            
            # Upload converted PNG to Telegram
            png_file = BytesIO(png_content)
            png_file.name = 'sticker.png'
            
            # Send as document to get file_id
            sent_msg = await message.reply_document(
                document=png_file,
                caption=f"✅ Converted from {media_type} to PNG (512x512)"
            )
            
            # Get the file_id of uploaded PNG
            png_file_id = sent_msg.document.file_id
            
            # Add to pack
            items = pack.get('items', [])
            items.append({'type': 'png_sticker', 'file_id': png_file_id})
            pack['items'] = items
            save_pack(pack_name, pack)
            
            await message.reply_text(f"✅ Added! ({len(items)} total)")
            
        except Exception as e:
            logger.error(f"Conversion error: {e}")
            await message.reply_text(f"❌ Error converting: {str(e)}")
        
        return
    
    await message.reply_text("Use /start", reply_markup=main_menu())

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
        await update.message.reply_text("❌ Add at least 1 item!")
        return
    
    await update.message.reply_text(
        f"📦 **Pack ready!**\n\n"
        f"Name: {pack_name}\n"
        f"Items: {len(items)}\n\n"
        f"✅ All items converted to PNG!\n"
        f"Click publish to create!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 Publish Pack", callback_data=f'publish_pack_{pack_name}')],
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
    await update.message.reply_text("❌ Cancelled!", reply_markup=main_menu())

# ============ MAIN ============
def main():
    try:
        print("\n" + "="*50)
        print("🤖 Starting Sticker Pack Bot...")
        print("="*50)
        print(f"🔑 Token: {TOKEN[:10]}...{TOKEN[-5:]}")
        print(f"📊 Database: {DATABASE}")
        print("="*50 + "\n")
        
        # Create application
        application = Application.builder().token(TOKEN).build()
        
        # Add handlers
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("done", done))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(
            filters.PHOTO | filters.VIDEO | filters.Sticker.ALL, 
            handle_message
        ))
        
        # Start the bot
        print("✅ Bot is running! Press Ctrl+C to stop.")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"❌ Failed to start bot: {e}")
        print(f"\n❌ Error: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
