import os
import sys
import json
import logging
import sqlite3
import requests
import subprocess
import tempfile
from datetime import datetime
from io import BytesIO
from PIL import Image, ImageOps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from telegram.constants import ParseMode

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8799309309:AAEy_csS6ESN8NObQlxHMss5YPmYEGOEtcc"
BOT_USERNAME = "@AryaStark_Devil_Bot"

if not TOKEN:
    logger.error("❌ Invalid token!")
    sys.exit(1)

DATABASE = 'packs.db'
TEMP_DIR = 'temp'
os.makedirs(TEMP_DIR, exist_ok=True)

# ============ CHECK FFMPEG ============
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], capture_output=True, timeout=5)
        return True
    except:
        return False

FFMPEG_AVAILABLE = check_ffmpeg()
logger.info(f"✅ FFmpeg: {'Available' if FFMPEG_AVAILABLE else 'Not available'}")

# ============ DATABASE ============
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS packs
                 (pack_name TEXT PRIMARY KEY, creator TEXT, items TEXT, 
                  published INTEGER, link TEXT, created TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_packs
                 (user_id TEXT, pack_name TEXT, PRIMARY KEY (user_id, pack_name))''')
    conn.commit()
    conn.close()

def get_pack(pack_name):
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

# ============ VIDEO PROCESSOR ============
def process_video_to_webm(file_content):
    """Convert video to WEBM - exactly 3 seconds"""
    try:
        if not FFMPEG_AVAILABLE:
            raise Exception("FFmpeg not installed!")
        
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(file_content)
            input_path = f.name
        
        output_path = input_path + '.webm'
        
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', '3',
            '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2,fps=30',
            '-c:v', 'libvpx-vp9',
            '-b:v', '0',
            '-crf', '30',
            '-pix_fmt', 'yuva420p',
            '-an',
            '-y',
            output_path
        ]
        
        subprocess.run(cmd, capture_output=True, timeout=120)
        
        with open(output_path, 'rb') as f:
            webm_content = f.read()
        
        os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        if len(webm_content) == 0:
            raise Exception("Video processing failed")
        
        return webm_content
        
    except Exception as e:
        logger.error(f"Video error: {e}")
        raise e

def process_photo_to_png(file_content):
    """Convert photo to PNG"""
    try:
        image = Image.open(BytesIO(file_content))
        if image.mode in ('RGBA', 'LA', 'P'):
            image = image.convert('RGB')
        image = ImageOps.fit(image, (512, 512), Image.Resampling.LANCZOS)
        output = BytesIO()
        image.save(output, format='PNG', optimize=True)
        return output.getvalue()
    except Exception as e:
        logger.error(f"Photo error: {e}")
        raise e

# ============ USER STATES ============
user_steps = {}
user_data = {}

def main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Create Sticker Pack", callback_data='create_pack')],
        [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
        [InlineKeyboardButton("ℹ️ Help", callback_data='help')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_username = context.bot.username
    msg = f"""👋 **Welcome to Sticker Pack Bot!**

✅ Video → 3 sec Video Sticker
✅ Photo → Static Sticker
✅ Sticker → Same format

📌 Just send a name - Bot adds `_by_{bot_username}`"""

    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())
    else:
        await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN, reply_markup=main_menu())

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == 'create_pack':
        await query.edit_message_text(
            f"📦 **Send your pack name**\n\nExample: `my_pack`\n\nBot adds `_by_botusername` automatically",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]])
        )
        user_steps[user_id] = 'waiting_for_name'
    
    elif query.data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif query.data == 'help':
        await query.edit_message_text(
            "📖 **How to use:**\n\n1️⃣ Click 'Create Sticker Pack'\n2️⃣ Send any name\n3️⃣ Send photo/video/sticker\n4️⃣ Type /done to publish!\n\n✅ Pack auto-publishes when you type /done",
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

async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    query = update.callback_query
    packs = get_user_packs(user_id)
    
    if not packs:
        await query.edit_message_text("📭 No packs!", reply_markup=main_menu())
        return
    
    keyboard = []
    for pack in packs:
        pack_data = get_pack(pack)
        if pack_data:
            status = "✅" if pack_data.get('published') else "⏳"
            keyboard.append([InlineKeyboardButton(f"{status} {pack}", callback_data=f'view_pack_{pack}')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')])
    await query.edit_message_text("📋 Your Packs:", reply_markup=InlineKeyboardMarkup(keyboard))

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
            keyboard.append([InlineKeyboardButton("🚀 Publish Now", callback_data=f'publish_now_{pack_name}')])
    else:
        keyboard.append([InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')])
    
    keyboard.append([InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_pack_{pack_name}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_packs')])
    
    status = "✅ Published" if published else "⏳ Draft"
    await query.edit_message_text(
        f"📦 **{pack_name}**\n\nStatus: {status}\nItems: {len(items)}",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

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
            [InlineKeyboardButton("📦 Open Pack", url=link)],
            [InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]
        ])
    )

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
async def publish_pack_now(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    await query.edit_message_text("⏳ Publishing...")
    await do_publish(update, context, user_id, pack_name)

async def do_publish(update, context, user_id, pack_name):
    """Actual publish function"""
    pack = get_pack(pack_name)
    if not pack or pack['creator'] != user_id:
        await update.effective_message.reply_text("❌ Pack not found!")
        return
    
    items = pack.get('items', [])
    if not items:
        await update.effective_message.reply_text("❌ Add at least 1 item!")
        return
    
    try:
        # Get first item
        first_item = items[0]
        file_id = first_item.get('file_id')
        file_info = await context.bot.get_file(file_id)
        file_content = await file_info.download_as_bytearray()
        sticker_type = first_item.get('sticker_type', 'png_sticker')
        
        # Create pack
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
        data = {
            'user_id': str(user_id),
            'name': pack_name,
            'title': pack_name.replace('_', ' ').title(),
            'emojis': '😀'
        }
        
        if sticker_type == 'webm_sticker':
            files = {'video_sticker': ('sticker.webm', BytesIO(file_content), 'video/webm')}
        else:
            files = {'png_sticker': ('sticker.png', BytesIO(file_content), 'image/png')}
        
        response = requests.post(api_url, data=data, files=files)
        result = response.json()
        
        if not result.get('ok'):
            error = result.get('description', str(result))
            if 'name is already occupied' in error:
                pack['published'] = True
                save_pack(pack_name, pack)
                return True
            else:
                await update.effective_message.reply_text(f"❌ Error: {error}")
                return False
        
        # Add remaining items
        for item in items[1:]:
            file_id = item.get('file_id')
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            sticker_type = item.get('sticker_type', 'png_sticker')
            
            add_url = f"https://api.telegram.org/bot{TOKEN}/addStickerToSet"
            add_data = {'user_id': str(user_id), 'name': pack_name, 'emojis': '😀'}
            
            if sticker_type == 'webm_sticker':
                add_files = {'video_sticker': ('sticker.webm', BytesIO(file_content), 'video/webm')}
            else:
                add_files = {'png_sticker': ('sticker.png', BytesIO(file_content), 'image/png')}
            
            requests.post(add_url, data=add_data, files=add_files)
        
        pack['published'] = True
        save_pack(pack_name, pack)
        return True
        
    except Exception as e:
        logger.error(f"Publish error: {e}")
        await update.effective_message.reply_text(f"❌ Error: {str(e)}")
        return False

# ============ ADD TO PACK ============
async def add_to_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    
    if user_id not in user_data:
        user_data[user_id] = {}
    user_data[user_id]['current_pack'] = pack_name
    user_steps[user_id] = 'waiting_for_media'
    
    await query.edit_message_text(
        f"📤 **Send Photo, Video, or Sticker**\n\n"
        f"✅ Video → 3 sec Video Sticker\n"
        f"✅ Photo → Static Sticker\n"
        f"✅ Sticker → Same format\n\n"
        f"Type /done to publish!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
    )

# ============ HANDLE MESSAGES ============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    if message.text and message.text.lower() == '/done':
        await done(update, context)
        return
    
    if user_id in user_steps and user_steps[user_id] == 'waiting_for_name':
        pack_name = message.text.strip().replace(' ', '_')
        bot_username = context.bot.username
        
        if not pack_name.endswith(f"_by_{bot_username}"):
            pack_name = f"{pack_name}_by_{bot_username}"
        pack_name = pack_name.replace('__', '_')
        
        if get_pack(pack_name):
            await message.reply_text("❌ Name already taken!")
            return
        
        data = {'creator': user_id, 'items': [], 'published': False,
                'link': f"https://t.me/addstickers/{pack_name}",
                'created': datetime.now().isoformat()}
        save_pack(pack_name, data)
        add_user_pack(user_id, pack_name)
        
        user_data[user_id] = {'current_pack': pack_name}
        user_steps[user_id] = 'waiting_for_media'
        
        await message.reply_text(
            f"✅ **Pack '{pack_name}' created!**\n\n"
            f"📤 Send **photo**, **video**, or **sticker**\n"
            f"Type /done to publish!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')]])
        )
        return
    
    if user_id in user_steps and user_steps[user_id] == 'waiting_for_media':
        pack_name = user_data.get(user_id, {}).get('current_pack')
        if not pack_name:
            await message.reply_text("❌ No pack found!")
            return
        
        pack = get_pack(pack_name)
        if not pack:
            await message.reply_text("❌ Pack not found!")
            return
        
        file_id = None
        sticker_type = 'png_sticker'
        media_type = 'unknown'
        processed_content = None
        
        try:
            if message.photo:
                file_id = message.photo[-1].file_id
                media_type = 'photo'
                await message.reply_text("🔄 Processing photo...")
                file_info = await context.bot.get_file(file_id)
                file_content = await file_info.download_as_bytearray()
                processed_content = process_photo_to_png(file_content)
                sticker_type = 'png_sticker'
                
            elif message.video:
                file_id = message.video.file_id
                media_type = 'video'
                duration = message.video.duration if message.video.duration else 0
                await message.reply_text(f"🔄 Processing video ({duration}s) → 3 sec...")
                file_info = await context.bot.get_file(file_id)
                file_content = await file_info.download_as_bytearray()
                processed_content = process_video_to_webm(file_content)
                sticker_type = 'webm_sticker'
                
            elif message.sticker:
                file_id = message.sticker.file_id
                media_type = 'sticker'
                await message.reply_text("🔄 Processing sticker...")
                file_info = await context.bot.get_file(file_id)
                file_content = await file_info.download_as_bytearray()
                
                if message.sticker.is_video:
                    processed_content = file_content
                    sticker_type = 'webm_sticker'
                else:
                    processed_content = file_content
                    sticker_type = 'png_sticker'
            
            else:
                await message.reply_text("❌ Send Photo, Video, or Sticker!")
                return
            
            if processed_content is None:
                await message.reply_text("❌ Failed to process!")
                return
            
            # Upload to Telegram
            if sticker_type == 'webm_sticker':
                file_name = 'sticker.webm'
            else:
                file_name = 'sticker.png'
            
            processed_file = BytesIO(processed_content)
            processed_file.name = file_name
            
            sent_msg = await message.reply_document(
                document=processed_file,
                filename=file_name,
                caption=f"✅ Added to {pack_name}!"
            )
            
            processed_file_id = sent_msg.document.file_id
            
            items = pack.get('items', [])
            items.append({
                'type': 'processed',
                'file_id': processed_file_id,
                'sticker_type': sticker_type,
                'original_type': media_type
            })
            pack['items'] = items
            save_pack(pack_name, pack)
            
            pack_link = f"https://t.me/addstickers/{pack_name}"
            
            await message.reply_text(
                f"✅ **Added to {pack_name}**\n\n"
                f"📦 Pack: `{pack_name}`\n"
                f"📊 Total: {len(items)} items\n"
                f"🔗 Link: `{pack_link}`\n\n"
                f"Type /done to publish!",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📦 Open Pack", url=pack_link)],
                    [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')]
                ])
            )
            
        except Exception as e:
            logger.error(f"Error: {e}")
            await message.reply_text(f"❌ Error: {str(e)}")
        
        return
    
    await message.reply_text("Use /start", reply_markup=main_menu())

# ============ DONE - AUTO PUBLISH ============
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
    
    await update.message.reply_text("⏳ Publishing your pack...")
    
    # Auto publish
    success = await do_publish(update, context, user_id, pack_name)
    
    if success:
        pack_link = f"https://t.me/addstickers/{pack_name}"
        await update.message.reply_text(
            f"✅ **Pack Published Successfully!**\n\n"
            f"📦 **Name:** `{pack_name}`\n"
            f"📊 **Items:** {len(items)}\n"
            f"🔗 **Link:** `{pack_link}`\n\n"
            f"🎉 Click the button below to add to Telegram!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📦 Open Pack", url=pack_link)],
                [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')]
            ])
        )
        
        # Clear user state
        if user_id in user_data:
            del user_data[user_id]
        if user_id in user_steps:
            del user_steps[user_id]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_steps:
        del user_steps[user_id]
    if user_id in user_data:
        del user_data[user_id]
    await update.message.reply_text("❌ Cancelled!", reply_markup=main_menu())

# ============ CALLBACK FOR PUBLISH NOW ============
async def publish_now_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    pack_name = query.data.replace('publish_now_', '')
    await publish_pack_now(update, context, user_id, pack_name)

# ============ MAIN ============
def main():
    try:
        print("\n" + "="*60)
        print("🤖 Sticker Pack Bot Starting...")
        print("="*60)
        print(f"🔑 Token: {TOKEN[:10]}...")
        print(f"🤖 Bot: {BOT_USERNAME}")
        print(f"✅ FFmpeg: {'Available' if FFMPEG_AVAILABLE else 'Not available'}")
        print("="*60 + "\n")
        
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CommandHandler("done", done))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(CallbackQueryHandler(publish_now_handler, pattern='^publish_now_'))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Sticker.ALL, handle_message))
        
        print("✅ Bot is running!")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
