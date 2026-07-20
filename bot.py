import os
import json
import logging
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

# Bot token from environment variable
TOKEN = os.environ.get('BOT_TOKEN', '8799309309:AAEy_csS6ESN8NObQlxHMss5YPmYEGOEtcc')

# Data storage file
DATA_FILE = 'pack_data.json'

# Load or create data
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {'sticker_packs': {}, 'emoji_packs': {}, 'user_packs': {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Initialize data
data = load_data()

# User states for pack creation
user_states = {}

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    
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
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👋 Welcome to Sticker & Emoji Pack Bot!\n\n"
        "I can help you create and manage your own sticker and emoji packs.\n"
        "Choose an option below:",
        reply_markup=reply_markup
    )

# Handle callback queries
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data = query.data
    
    if data == 'create_sticker':
        await query.edit_message_text(
            "📦 **Create Sticker Pack**\n\n"
            "Please send me the **name** for your sticker pack.\n"
            "Example: `My Cool Stickers`\n\n"
            "Type /cancel to cancel the process.",
            parse_mode=ParseMode.MARKDOWN
        )
        user_states[user_id] = 'awaiting_sticker_name'
    
    elif data == 'create_emoji':
        await query.edit_message_text(
            "🎨 **Create Emoji Pack**\n\n"
            "Please send me the **name** for your emoji pack.\n"
            "Example: `Funny Emojis`\n\n"
            "Type /cancel to cancel the process.",
            parse_mode=ParseMode.MARKDOWN
        )
        user_states[user_id] = 'awaiting_emoji_name'
    
    elif data == 'my_packs':
        await show_my_packs(update, context, user_id)
    
    elif data == 'help':
        await query.edit_message_text(
            "ℹ️ **How to use this bot:**\n\n"
            "1. Click 'Create Sticker Pack' to create a sticker pack\n"
            "2. Click 'Create Emoji Pack' to create an emoji pack\n"
            "3. Send images/videos/stickers to add to your packs\n"
            "4. Use 'My Packs' to view and manage your packs\n\n"
            "**Features:**\n"
            "✅ Create unlimited packs\n"
            "✅ Add photos, videos, and stickers\n"
            "✅ Get shareable links\n"
            "✅ Manage your packs easily",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith('view_pack_'):
        pack_type, pack_name = data.replace('view_pack_', '').split('_', 1)
        await view_pack(update, context, user_id, pack_type, pack_name)
    
    elif data.startswith('add_to_pack_'):
        pack_type, pack_name = data.replace('add_to_pack_', '').split('_', 1)
        user_states[user_id] = f'adding_to_{pack_type}_{pack_name}'
        await query.edit_message_text(
            f"📤 **Adding to {pack_type} pack: {pack_name}**\n\n"
            "Send me a photo, video, or sticker to add to this pack.\n"
            "Type /cancel to cancel.",
            parse_mode=ParseMode.MARKDOWN
        )
    
    elif data.startswith('delete_pack_'):
        pack_type, pack_name = data.replace('delete_pack_', '').split('_', 1)
        await delete_pack(update, context, user_id, pack_type, pack_name)

# Show user's packs
async def show_my_packs(update, context, user_id):
    query = update.callback_query
    user_packs = data['user_packs'].get(user_id, {'sticker': [], 'emoji': []})
    
    if not user_packs['sticker'] and not user_packs['emoji']:
        await query.edit_message_text(
            "📭 You don't have any packs yet!\n\n"
            "Click 'Create Sticker Pack' or 'Create Emoji Pack' to get started."
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

# View specific pack
async def view_pack(update, context, user_id, pack_type, pack_name):
    query = update.callback_query
    
    if pack_type == 'sticker':
        pack_data = data['sticker_packs'].get(pack_name, {})
    else:
        pack_data = data['emoji_packs'].get(pack_name, {})
    
    if not pack_data or pack_data.get('creator') != user_id:
        await query.edit_message_text("❌ Pack not found or you don't have permission!")
        return
    
    items_count = len(pack_data.get('items', []))
    pack_link = pack_data.get('link', 'Not set')
    
    keyboard = [
        [InlineKeyboardButton("📤 Add Item", callback_data=f'add_to_pack_{pack_type}_{pack_name}')],
        [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_{pack_type}_{pack_name}')],
        [InlineKeyboardButton("🗑️ Delete Pack", callback_data=f'delete_pack_{pack_type}_{pack_name}')],
        [InlineKeyboardButton("🔙 Back to My Packs", callback_data='my_packs')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"📦 **{pack_type.title()} Pack: {pack_name}**\n\n"
        f"📊 Items: {items_count}\n"
        f"🔗 Link: {pack_link}\n\n"
        f"What would you like to do?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=reply_markup
    )

# Delete pack
async def delete_pack(update, context, user_id, pack_type, pack_name):
    query = update.callback_query
    
    if pack_type == 'sticker':
        if pack_name in data['sticker_packs']:
            del data['sticker_packs'][pack_name]
    else:
        if pack_name in data['emoji_packs']:
            del data['emoji_packs'][pack_name]
    
    if user_id in data['user_packs']:
        if pack_type in data['user_packs'][user_id]:
            if pack_name in data['user_packs'][user_id][pack_type]:
                data['user_packs'][user_id][pack_type].remove(pack_name)
    
    save_data(data)
    
    await query.edit_message_text(
        f"✅ Pack '{pack_name}' has been deleted successfully!"
    )

# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    # Check if user is in a state
    if user_id not in user_states:
        await message.reply_text(
            "Please use the buttons to create a pack first!\n"
            "Type /start to begin."
        )
        return
    
    state = user_states[user_id]
    
    if state == 'awaiting_sticker_name':
        pack_name = message.text.strip()
        if not pack_name:
            await message.reply_text("Please send a valid name!")
            return
        
        if pack_name in data['sticker_packs']:
            await message.reply_text("❌ A sticker pack with this name already exists!")
            return
        
        # Create sticker pack
        data['sticker_packs'][pack_name] = {
            'creator': user_id,
            'items': [],
            'link': f"https://t.me/addstickers/{pack_name.replace(' ', '_')}",
            'created': datetime.now().isoformat()
        }
        
        if user_id not in data['user_packs']:
            data['user_packs'][user_id] = {'sticker': [], 'emoji': []}
        data['user_packs'][user_id]['sticker'].append(pack_name)
        save_data(data)
        
        del user_states[user_id]
        
        await message.reply_text(
            f"✅ Sticker pack '{pack_name}' created successfully!\n\n"
            f"🔗 Link: {data['sticker_packs'][pack_name]['link']}\n\n"
            "Send me photos/videos/stickers to add to this pack!\n"
            "Type /start to go back to main menu."
        )
    
    elif state == 'awaiting_emoji_name':
        pack_name = message.text.strip()
        if not pack_name:
            await message.reply_text("Please send a valid name!")
            return
        
        if pack_name in data['emoji_packs']:
            await message.reply_text("❌ An emoji pack with this name already exists!")
            return
        
        # Create emoji pack
        data['emoji_packs'][pack_name] = {
            'creator': user_id,
            'items': [],
            'link': f"https://t.me/addemoji/{pack_name.replace(' ', '_')}",
            'created': datetime.now().isoformat()
        }
        
        if user_id not in data['user_packs']:
            data['user_packs'][user_id] = {'sticker': [], 'emoji': []}
        data['user_packs'][user_id]['emoji'].append(pack_name)
        save_data(data)
        
        del user_states[user_id]
        
        await message.reply_text(
            f"✅ Emoji pack '{pack_name}' created successfully!\n\n"
            f"🔗 Link: {data['emoji_packs'][pack_name]['link']}\n\n"
            "Send me photos/videos/stickers to add to this pack!\n"
            "Type /start to go back to main menu."
        )
    
    elif state.startswith('adding_to_'):
        # Add item to pack
        _, pack_type, pack_name = state.split('_', 2)
        
        if pack_type == 'sticker':
            pack_data = data['sticker_packs'].get(pack_name)
        else:
            pack_data = data['emoji_packs'].get(pack_name)
        
        if not pack_data or pack_data.get('creator') != user_id:
            await message.reply_text("❌ Pack not found or you don't have permission!")
            del user_states[user_id]
            return
        
        # Handle different media types
        item_data = {}
        
        if message.photo:
            file_id = message.photo[-1].file_id
            item_data = {'type': 'photo', 'file_id': file_id}
        elif message.video:
            file_id = message.video.file_id
            item_data = {'type': 'video', 'file_id': file_id}
        elif message.sticker:
            file_id = message.sticker.file_id
            item_data = {'type': 'sticker', 'file_id': file_id}
        elif message.document:
            file_id = message.document.file_id
            item_data = {'type': 'document', 'file_id': file_id}
        else:
            await message.reply_text(
                "❌ Please send a photo, video, or sticker!\n"
                "Type /cancel to cancel."
            )
            return
        
        pack_data['items'].append(item_data)
        save_data(data)
        
        await message.reply_text(
            f"✅ Item added to {pack_type} pack '{pack_name}'!\n\n"
            f"Total items: {len(pack_data['items'])}\n"
            "Send more items or type /start to go back."
        )

# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        await update.message.reply_text(
            "❌ Process cancelled!\n"
            "Type /start to begin again."
        )
    else:
        await update.message.reply_text("No active process to cancel.")

# Back to main
async def back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await start(update, context)

# Main function
def main():
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(CallbackQueryHandler(back_to_main, pattern='^back_to_main$'))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Sticker.ALL | filters.Document.ALL, handle_message))
    
    # Start the bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
