import os
import sys
import json
import logging
import sqlite3
import requests
import subprocess
import tempfile
import re
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
    c.execute('''CREATE TABLE IF NOT EXISTS selected_pack
                 (user_id TEXT PRIMARY KEY, pack_name TEXT)''')
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

def get_selected_pack(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT pack_name FROM selected_pack WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else None

def set_selected_pack(user_id, pack_name):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO selected_pack (user_id, pack_name) VALUES (?, ?)", (user_id, pack_name))
    conn.commit()
    conn.close()

def clear_selected_pack(user_id):
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM selected_pack WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()

init_db()

# ============ VIDEO PROCESSOR - ONLY CUT TO 3 SEC ============
def cut_video_to_3sec(file_content):
    """Only cut video to 3 seconds - NO CONVERSION TO PNG"""
    try:
        if not FFMPEG_AVAILABLE:
            raise Exception("FFmpeg not installed!")
        
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as f:
            f.write(file_content)
            input_path = f.name
        
        output_path = input_path + '_cut.mp4'
        
        # Only cut to 3 seconds, keep original format
        cmd = [
            'ffmpeg', '-i', input_path,
            '-t', '3',
            '-c', 'copy',
            '-y',
            output_path
        ]
        
        subprocess.run(cmd, capture_output=True, timeout=60)
        
        # If copy fails, try re-encode
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            cmd = [
                'ffmpeg', '-i', input_path,
                '-t', '3',
                '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2',
                '-c:v', 'libx264',
                '-crf', '23',
                '-preset', 'fast',
                '-y',
                output_path
            ]
            subprocess.run(cmd, capture_output=True, timeout=60)
        
        with open(output_path, 'rb') as f:
            video_content = f.read()
        
        os.unlink(input_path)
        if os.path.exists(output_path):
            os.unlink(output_path)
        
        if len(video_content) == 0:
            raise Exception("Video cutting failed")
        
        return video_content
        
    except Exception as e:
        logger.error(f"Video cut error: {e}")
        raise e

# ============ PUBLISH PACK ============
async def publish_pack(pack_name, user_id, context):
    """Publish the pack - First sticker MUST be static sticker"""
    pack = get_pack(pack_name)
    if not pack or pack['creator'] != user_id:
        return False, "Pack not found!"
    
    items = pack.get('items', [])
    if not items:
        return False, "Add at least 1 item!"
    
    try:
        # Get first item - MUST be static sticker (PNG)
        first_item = items[0]
        first_file_id = first_item.get('file_id')
        first_sticker_type = first_item.get('sticker_type', 'png_sticker')
        
        # If first item is video, we need a static sticker first
        if first_sticker_type == 'webm_sticker':
            # Extract first frame as PNG for first sticker
            file_info = await context.bot.get_file(first_file_id)
            file_content = await file_info.download_as_bytearray()
            
            with tempfile.NamedTemporaryFile(suffix='.webm', delete=False) as f:
                f.write(file_content)
                video_path = f.name
            
            png_path = video_path + '.png'
            cmd = ['ffmpeg', '-i', video_path, '-vframes', '1', '-vf', 'scale=512:512:force_original_aspect_ratio=decrease,pad=512:512:(ow-iw)/2:(oh-ih)/2', '-y', png_path]
            subprocess.run(cmd, capture_output=True, timeout=30)
            
            with open(png_path, 'rb') as f:
                png_content = f.read()
            
            os.unlink(video_path)
            if os.path.exists(png_path):
                os.unlink(png_path)
            
            png_file = BytesIO(png_content)
            png_file.name = 'sticker.png'
            
            sent_msg = await context.bot.send_document(
                chat_id=user_id,
                document=png_file,
                filename='sticker.png'
            )
            
            first_file_id = sent_msg.document.file_id
            first_sticker_type = 'png_sticker'
        
        # Get file content for first sticker
        file_info = await context.bot.get_file(first_file_id)
        file_content = await file_info.download_as_bytearray()
        
        # Create pack with static sticker as first
        api_url = f"https://api.telegram.org/bot{TOKEN}/createNewStickerSet"
        data = {
            'user_id': str(user_id),
            'name': pack_name,
            'title': pack_name.replace('_', ' ').title(),
            'emojis': '😀'
        }
        files = {'png_sticker': ('sticker.png', BytesIO(file_content), 'image/png')}
        
        response = requests.post(api_url, data=data, files=files)
        result = response.json()
        
        if not result.get('ok'):
            error = result.get('description', str(result))
            if 'name is already occupied' in error:
                pack['published'] = True
                save_pack(pack_name, pack)
                return True, "Pack already exists!"
            else:
                return False, f"Error: {error}"
        
        # Add remaining items
        for i, item in enumerate(items):
            if i == 0:
                continue
            
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
        return True, "Published successfully!"
        
    except Exception as e:
        logger.error(f"Publish error: {e}")
        return False, f"Error: {str(e)}"

# ============ USER STATES ============
user_steps = {}
user_data = {}

def main_menu():
    keyboard = [
        [InlineKeyboardButton("📦 Create New Pack", callback_data='create_pack')],
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

📌 Create a pack, select it, and send media!
Bot adds `_by_{bot_username}` automatically"""

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
            f"📦 **Send your pack name**\n\n"
            f"Only letters, numbers, underscores\n"
            f"Example: `my_pack`\n\n"
            f"Bot adds `_by_botusername` automatically",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')]])
        )
        user_steps[user_id] = 'waiting_for_name'
    
    elif query.data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif query.data == 'help':
        await query.edit_message_text(
            "📖 **How to use:**\n\n"
            "1️⃣ Create a pack\n"
            "2️⃣ Select it from 'My Packs'\n"
            "3️⃣ Send photo/video/sticker\n"
            "4️⃣ Auto-publishes!\n\n"
            "✅ Video auto-cut to 3 seconds!",
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
    
    elif query.data.startswith('select_pack_'):
        pack_name = query.data.replace('select_pack_', '')
        set_selected_pack(user_id, pack_name)
        await query.edit_message_text(
            f"✅ **Selected: {pack_name}**\n\n"
            f"Now send any **photo**, **video**, or **sticker**\n"
            f"It will be added to this pack!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')],
                [InlineKeyboardButton("🔙 Back", callback_data='my_packs')]
            ])
        )

async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id):
    query = update.callback_query
    packs = get_user_packs(user_id)
    selected = get_selected_pack(user_id)
    
    if not packs:
        await query.edit_message_text("📭 No packs! Create one first.", reply_markup=main_menu())
        return
    
    keyboard = []
    for pack in packs:
        pack_data = get_pack(pack)
        if pack_data:
            status = "✅" if pack_data.get('published') else "⏳"
            selected_mark = "⭐ " if pack == selected else ""
            keyboard.append([
                InlineKeyboardButton(f"{selected_mark}{status} {pack}", callback_data=f'view_pack_{pack}')
            ])
            if pack != selected:
                keyboard.append([
                    InlineKeyboardButton(f"📌 Select {pack}", callback_data=f'select_pack_{pack}')
                ])
    
    if selected:
        keyboard.append([InlineKeyboardButton(f"📍 Currently selected: {selected}", callback_data='dummy')])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='back_to_menu')])
    await query.edit_message_text(
        f"📋 **Your Packs:**\n\n⭐ = Selected (media will add here)\n✅ = Published | ⏳ = Draft",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    items = pack.get('items', [])
    published = pack.get('published', False)
    selected = get_selected_pack(user_id)
    
    keyboard = []
    if not published:
        keyboard.append([InlineKeyboardButton("📤 Add Media", callback_data=f'add_to_pack_{pack_name}')])
    else:
        keyboard.append([InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_name}')])
    
    if pack_name != selected:
        keyboard.append([InlineKeyboardButton("⭐ Select This Pack", callback_data=f'select_pack_{pack_name}')])
    else:
        keyboard.append([InlineKeyboardButton("📍 Currently Selected", callback_data='dummy')])
    
    keyboard.append([InlineKeyboardButton("🗑️ Delete", callback_data=f'delete_pack_{pack_name}')])
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data='my_packs')])
    
    status = "✅ Published" if published else "⏳ Draft"
    await query.edit_message_text(
        f"📦 **{pack_name}**\n\n"
        f"Status: {status}\n"
        f"Items: {len(items)}\n\n"
        f"⭐ Select this pack to auto-add media!",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def get_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    pack = get_pack(pack_name)
    
    if not pack or pack['creator'] != user_id:
        await query.edit_message_text("❌ Pack not found!", reply_markup=main_menu())
        return
    
    link = f"https://t.me/addstickers/{pack_name}"
    pack_display = pack_name.replace('_by_', ' :: @')
    
    await query.edit_message_text(
        f"🔗 **Your Pack Link:**\n\n`{link}`\n\n✅ Click to add to Telegram!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"📦 {pack_display}", url=link)],
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
    selected = get_selected_pack(user_id)
    if selected == pack_name:
        clear_selected_pack(user_id)
    await query.edit_message_text("✅ Deleted!", reply_markup=main_menu())

async def add_to_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_name):
    query = update.callback_query
    
    set_selected_pack(user_id, pack_name)
    user_steps[user_id] = 'waiting_for_media'
    
    await query.edit_message_text(
        f"📤 **Pack selected: {pack_name}**\n\n"
        f"Now send any **photo**, **video**, or **sticker**\n"
        f"It will be added automatically!",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f'view_pack_{pack_name}')]])
    )

# ============ HANDLE MESSAGES ============
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    if user_id in user_steps and user_steps[user_id] == 'waiting_for_name':
        pack_name = message.text.strip().replace(' ', '_')
        bot_username = context.bot.username
        
        # Clean pack name - only letters, numbers, underscore
        pack_name = re.sub(r'[^a-zA-Z0-9_]', '', pack_name)
        
        if not pack_name:
            await message.reply_text("❌ Invalid name! Use letters, numbers, underscores only.")
            return
        
        if not pack_name[0].isalpha():
            await message.reply_text("❌ Name must start with a letter!")
            return
        
        if not pack_name.endswith(f"_by_{bot_username}"):
            pack_name = f"{pack_name}_by_{bot_username}"
        
        if get_pack(pack_name):
            await message.reply_text("❌ Name already taken!")
            return
        
        data = {'creator': user_id, 'items': [], 'published': False,
                'link': f"https://t.me/addstickers/{pack_name}",
                'created': datetime.now().isoformat()}
        save_pack(pack_name, data)
        add_user_pack(user_id, pack_name)
        set_selected_pack(user_id, pack_name)
        
        user_data[user_id] = {'current_pack': pack_name}
        user_steps[user_id] = 'waiting_for_media'
        
        await message.reply_text(
            f"✅ **Pack '{pack_name}' created!**\n\n"
            f"⭐ Selected automatically!\n"
            f"Now send **photo**, **video**, or **sticker**\n"
            f"It will be added and published!",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📋 View Pack", callback_data=f'view_pack_{pack_name}')],
                [InlineKeyboardButton("📦 Open Pack", url=f"https://t.me/addstickers/{pack_name}")]
            ])
        )
        return
    
    # Check if user has a selected pack
    selected_pack = get_selected_pack(user_id)
    
    if not selected_pack:
        await message.reply_text(
            "❌ No pack selected!\n\n"
            "Create a pack or select one from 'My Packs'",
            reply_markup=main_menu()
        )
        return
    
    pack = get_pack(selected_pack)
    if not pack or pack['creator'] != user_id:
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
            # Photo - directly use as PNG sticker
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            # Just resize to 512x512, keep as PNG
            image = Image.open(BytesIO(file_content))
            if image.mode in ('RGBA', 'LA', 'P'):
                image = image.convert('RGB')
            image = ImageOps.fit(image, (512, 512), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format='PNG', optimize=True)
            processed_content = output.getvalue()
            sticker_type = 'png_sticker'
            
        elif message.video:
            file_id = message.video.file_id
            media_type = 'video'
            # Video - ONLY cut to 3 seconds, NO CONVERSION
            file_info = await context.bot.get_file(file_id)
            file_content = await file_info.download_as_bytearray()
            
            # Cut video to 3 seconds
            processed_content = cut_video_to_3sec(file_content)
            sticker_type = 'webm_sticker'
            
        elif message.sticker:
            file_id = message.sticker.file_id
            media_type = 'sticker'
            # Sticker - use as-is
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
            caption=f"✅ Added to {selected_pack}!"
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
        save_pack(selected_pack, pack)
        
        # Auto publish
        await message.reply_text("⏳ Publishing...")
        success, msg_result = await publish_pack(selected_pack, user_id, context)
        
        if success:
            pack_link = f"https://t.me/addstickers/{selected_pack}"
            pack_display = selected_pack.replace('_by_', ' :: @')
            
            await message.reply_text(
                f"✅ **Added to {pack_display}**\n\n"
                f"You can send emoji for this sticker\n\n"
                f"📦 **{pack_display}**",
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(f"📦 {pack_display}", url=pack_link)],
                    [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')]
                ])
            )
        else:
            await message.reply_text(f"❌ {msg_result}")
        
    except Exception as e:
        logger.error(f"Error: {e}")
        await message.reply_text(f"❌ Error: {str(e)}")

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
        print("\n" + "="*60)
        print("🤖 Sticker Pack Bot Starting...")
        print("="*60)
        print(f"🔑 Token: {TOKEN[:10]}...")
        print(f"🤖 Bot: {BOT_USERNAME}")
        print(f"✅ FFmpeg: {'Available' if FFMPEG_AVAILABLE else 'Not available'}")
        print("="*60 + "\n")
        print("✅ Video → 3 sec cut (NO CONVERSION)")
        print("✅ Photo → Static sticker")
        print("✅ Sticker → Same format")
        print("✅ Auto-publish: ON")
        print("="*60 + "\n")
        
        application = Application.builder().token(TOKEN).build()
        application.add_handler(CommandHandler("start", start))
        application.add_handler(CommandHandler("cancel", cancel))
        application.add_handler(CallbackQueryHandler(button_handler))
        application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Sticker.ALL, handle_message))
        
        print("✅ Bot is running!")
        application.run_polling()
        
    except Exception as e:
        logger.error(f"Failed: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
