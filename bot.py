import os
import json
import logging
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

# Bot token from environment variable
TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')

# Data storage file
DATA_FILE = 'pack_data.json'

# Load or create data
def load_data():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {'sticker_packs': {}, 'emoji_packs': {}, 'user_packs': {}}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)

# Initialize data
data = load_data()

# User states
user_states = {}

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

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        await query.edit_message_text(
            "👋 Welcome to Sticker & Emoji Pack Bot!\n\n"
            "I can help you create and manage your own sticker and emoji packs.\n"
            "Choose an option below:",
            reply_markup=get_main_menu()
        )
    else:
        await update.message.reply_text(
            "👋 Welcome to Sticker & Emoji Pack Bot!\n\n"
            "I can help you create and manage your own sticker and emoji packs.\n"
            "Choose an option below:",
            reply_markup=get_main_menu()
        )

# Handle callback queries
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = str(query.from_user.id)
    data_callback = query.data
    
    if data_callback == 'create_sticker':
        await query.edit_message_text(
            "📦 **Create Sticker Pack**\n\n"
            "Please send me the **name** for your sticker pack.\n"
            "Example: `MyCoolStickers`\n\n"
            "⚠️ Name should be without spaces (use underscores or camelCase)\n"
            "Type /cancel to cancel.",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='back_to_main')]])
        )
        user_states[user_id] = 'awaiting_sticker_name'
    
    elif data_callback == 'create_emoji':
        await query.edit_message_text(
            "🎨 **Create Emoji Pack**\n\n"
            "Please send me the **name** for your emoji pack.\n"
            "Example: `MyFunnyEmojis`\n\n"
            "⚠️ Name should be without spaces (use underscores or camelCase)\n"
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
            "1. Click 'Create Sticker Pack' to create a sticker pack\n"
            "2. Click 'Create Emoji Pack' to create an emoji pack\n"
            "3. Send images to add to sticker packs\n"
            "4. Send images/videos/stickers to add to emoji packs\n"
            "5. Use 'My Packs' to view and manage your packs\n\n"
            "**Sticker Pack:** Only images/stickers allowed\n"
            "**Emoji Pack:** Images, videos, and stickers allowed\n\n"
            "**Get Real Pack Link:**\n"
            "- For stickers: Use @Stickers bot\n"
            "- For emojis: Use @Emoji bot",
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
            user_states[user_id] = f'adding_to_{pack_type}_{pack_name}'
            
            if pack_type == 'sticker':
                msg = f"📤 **Adding to Sticker Pack: {pack_name}**\n\nSend me a **photo** or **sticker** to add to this pack.\nType /cancel to cancel."
            else:
                msg = f"📤 **Adding to Emoji Pack: {pack_name}**\n\nSend me a **photo**, **video**, or **sticker** to add to this pack.\nType /cancel to cancel."
            
            await query.edit_message_text(
                msg,
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

# Show user's packs
async def show_my_packs(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id=None):
    if not user_id:
        user_id = str(update.effective_user.id)
    
    query = update.callback_query
    user_packs = data['user_packs'].get(user_id, {'sticker': [], 'emoji': []})
    
    if not user_packs['sticker'] and not user_packs['emoji']:
        await query.edit_message_text(
            "📭 You don't have any packs yet!\n\n"
            "Click 'Create Sticker Pack' or 'Create Emoji Pack' to get started.",
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

# View specific pack
async def view_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
    query = update.callback_query
    
    if pack_type == 'sticker':
        pack_data = data['sticker_packs'].get(pack_name, {})
    else:
        pack_data = data['emoji_packs'].get(pack_name, {})
    
    if not pack_data or pack_data.get('creator') != user_id:
        await query.edit_message_text(
            "❌ Pack not found or you don't have permission!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data='my_packs')]])
        )
        return
    
    items_count = len(pack_data.get('items', []))
    pack_link = pack_data.get('link', 'Not set')
    
    keyboard = [
        [InlineKeyboardButton("📤 Add Item", callback_data=f'add_to_pack_{pack_type}_{pack_name}')],
        [InlineKeyboardButton("🔗 Get Shareable Link", callback_data=f'get_link_{pack_type}_{pack_name}')],
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

# Get pack link
async def get_pack_link(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
    query = update.callback_query
    
    if pack_type == 'sticker':
        pack_data = data['sticker_packs'].get(pack_name, {})
    else:
        pack_data = data['emoji_packs'].get(pack_name, {})
    
    if not pack_data:
        await query.edit_message_text("❌ Pack not found!")
        return
    
    link = pack_data.get('link', 'No link available')
    
    # For real Telegram packs, you need to register with @Stickers or @Emoji bot
    if pack_type == 'sticker':
        instructions = "To create a real sticker pack:\n1. Use @Stickers bot\n2. Send /newpack\n3. Follow the instructions"
    else:
        instructions = "To create a real emoji pack:\n1. Use @Emoji bot\n2. Send /newpack\n3. Follow the instructions"
    
    await query.edit_message_text(
        f"🔗 **{pack_type.title()} Pack Link**\n\n"
        f"📦 Pack: {pack_name}\n"
        f"🔗 Link: `{link}`\n\n"
        f"ℹ️ {instructions}\n\n"
        f"Note: This link will work after you register the pack with @Stickers or @Emoji bot.",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back to Pack", callback_data=f'view_pack_{pack_type}_{pack_name}')]
        ])
    )

# Delete pack
async def delete_pack(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id, pack_type, pack_name):
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
        f"✅ Pack '{pack_name}' has been deleted successfully!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to My Packs", callback_data='my_packs')]])
    )

# Handle messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    message = update.message
    
    # Check if user is in a state
    if user_id not in user_states:
        await message.reply_text(
            "Please use the buttons to create a pack first!\n"
            "Type /start to begin.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]])
        )
        return
    
    state = user_states[user_id]
    
    if state == 'awaiting_sticker_name':
        pack_name = message.text.strip().replace(' ', '_')
        if not pack_name:
            await message.reply_text("Please send a valid name!")
            return
        
        if pack_name in data['sticker_packs']:
            await message.reply_text("❌ A sticker pack with this name already exists! Please choose another name.")
            return
        
        # Create sticker pack
        data['sticker_packs'][pack_name] = {
            'creator': user_id,
            'items': [],
            'link': f"https://t.me/addstickers/{pack_name}",
            'created': datetime.now().isoformat()
        }
        
        if user_id not in data['user_packs']:
            data['user_packs'][user_id] = {'sticker': [], 'emoji': []}
        data['user_packs'][user_id]['sticker'].append(pack_name)
        save_data(data)
        
        del user_states[user_id]
        
        keyboard = [
            [InlineKeyboardButton("📤 Add Sticker", callback_data=f'add_to_pack_sticker_{pack_name}')],
            [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_sticker_{pack_name}')],
            [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
        ]
        
        await message.reply_text(
            f"✅ Sticker pack '{pack_name}' created successfully!\n\n"
            f"🔗 Link: `{data['sticker_packs'][pack_name]['link']}`\n\n"
            "Send me photos or stickers to add to this pack!\n"
            "Or use the buttons below:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif state == 'awaiting_emoji_name':
        pack_name = message.text.strip().replace(' ', '_')
        if not pack_name:
            await message.reply_text("Please send a valid name!")
            return
        
        if pack_name in data['emoji_packs']:
            await message.reply_text("❌ An emoji pack with this name already exists! Please choose another name.")
            return
        
        # Create emoji pack
        data['emoji_packs'][pack_name] = {
            'creator': user_id,
            'items': [],
            'link': f"https://t.me/addemoji/{pack_name}",
            'created': datetime.now().isoformat()
        }
        
        if user_id not in data['user_packs']:
            data['user_packs'][user_id] = {'sticker': [], 'emoji': []}
        data['user_packs'][user_id]['emoji'].append(pack_name)
        save_data(data)
        
        del user_states[user_id]
        
        keyboard = [
            [InlineKeyboardButton("📤 Add Emoji", callback_data=f'add_to_pack_emoji_{pack_name}')],
            [InlineKeyboardButton("🔗 Get Link", callback_data=f'get_link_emoji_{pack_name}')],
            [InlineKeyboardButton("📋 My Packs", callback_data='my_packs')],
            [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
        ]
        
        await message.reply_text(
            f"✅ Emoji pack '{pack_name}' created successfully!\n\n"
            f"🔗 Link: `{data['emoji_packs'][pack_name]['link']}`\n\n"
            "Send me photos, videos, or stickers to add to this pack!\n"
            "Or use the buttons below:",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif state.startswith('adding_to_'):
        # Add item to pack
        parts = state.split('_', 2)
        if len(parts) < 3:
            return
        
        _, pack_type, pack_name = parts
        
        if pack_type == 'sticker':
            pack_data = data['sticker_packs'].get(pack_name)
            if not pack_data:
                await message.reply_text("❌ Sticker pack not found!")
                del user_states[user_id]
                return
            
            # Only allow photos and stickers for sticker packs
            if message.photo:
                file_id = message.photo[-1].file_id
                item_data = {'type': 'photo', 'file_id': file_id}
            elif message.sticker:
                file_id = message.sticker.file_id
                item_data = {'type': 'sticker', 'file_id': file_id}
            else:
                await message.reply_text(
                    "❌ Sticker packs only accept **photos** or **stickers**!\n"
                    "Please send a photo or sticker.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        else:  # emoji pack
            pack_data = data['emoji_packs'].get(pack_name)
            if not pack_data:
                await message.reply_text("❌ Emoji pack not found!")
                del user_states[user_id]
                return
            
            # Allow photos, videos, and stickers for emoji packs
            if message.photo:
                file_id = message.photo[-1].file_id
                item_data = {'type': 'photo', 'file_id': file_id}
            elif message.video:
                file_id = message.video.file_id
                item_data = {'type': 'video', 'file_id': file_id}
            elif message.sticker:
                file_id = message.sticker.file_id
                item_data = {'type': 'sticker', 'file_id': file_id}
            else:
                await message.reply_text(
                    "❌ Emoji packs accept **photos**, **videos**, or **stickers**!\n"
                    "Please send a valid media file.",
                    parse_mode=ParseMode.MARKDOWN
                )
                return
        
        if pack_data.get('creator') != user_id:
            await message.reply_text("❌ You don't have permission to add to this pack!")
            del user_states[user_id]
            return
        
        # Add item to pack
        pack_data['items'].append(item_data)
        save_data(data)
        
        # Keep the user in adding state
        await message.reply_text(
            f"✅ Item added to {pack_type} pack '{pack_name}'!\n\n"
            f"📊 Total items: {len(pack_data['items'])}\n"
            "Send more items or use the buttons below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Back to Pack", callback_data=f'view_pack_{pack_type}_{pack_name}')],
                [InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]
            ])
        )

# Cancel command
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.effective_user.id)
    if user_id in user_states:
        del user_states[user_id]
        await update.message.reply_text(
            "❌ Process cancelled!\n"
            "Type /start to begin again.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]])
        )
    else:
        await update.message.reply_text(
            "No active process to cancel.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Main Menu", callback_data='back_to_main')]])
        )

# Error handler
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error {context.error}")
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "❌ An error occurred! Please try again or type /start."
        )

# Main function
def main():
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("cancel", cancel))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Sticker.ALL, handle_message))
    
    # Add error handler
    application.add_error_handler(error_handler)
    
    # Start the bot
    print("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
