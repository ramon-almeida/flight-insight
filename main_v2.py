import os
from dotenv import load_dotenv
from serpapi import GoogleSearch
from datetime import datetime, timedelta
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()
api_key = os.getenv("SERPAPI_API_KEY")
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

CITY_TO_AIRPORT = {
    "Manchester": "MAN", "Sevilla": "SVQ", "Gdansk": "GDN",
    "Malaga": "AGP", "Faro": "FAO", "London": "LHR"
}

scheduler = AsyncIOScheduler()

DEPARTURE, ARRIVAL, OUTBOUND_DATE, RETURN_DATE = range(4)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()  # clear any previous data
    context.user_data['chat_id'] = update.message.chat_id
    await update.message.reply_text("🛫 Enter departure city (e.g., Manchester):")
    return DEPARTURE


async def departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip().title()
    if city not in CITY_TO_AIRPORT:
        available_cities = ', '.join(CITY_TO_AIRPORT.keys())
        await update.message.reply_text(
            f"⚠️ Invalid departure city. Available options:\n{available_cities}\n\nPlease enter again:"
        )
        return DEPARTURE
    context.user_data['departure_city'] = city
    await update.message.reply_text("🏙️ Enter arrival city (e.g., Sevilla):")
    return ARRIVAL


async def arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
    city = update.message.text.strip().title()
    if city not in CITY_TO_AIRPORT:
        available_cities = ', '.join(CITY_TO_AIRPORT.keys())
        await update.message.reply_text(
            f"⚠️ Invalid arrival city. Available options:\n{available_cities}\n\nPlease enter again:"
        )
        return ARRIVAL
    context.user_data['arrival_city'] = city
    await update.message.reply_text("📅 Enter departure date (YYYY-MM-DD):")
    return OUTBOUND_DATE


async def outbound_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    if not validate_date(date_text):
        await update.message.reply_text("⚠️ Invalid date format. Please enter date as YYYY-MM-DD:")
        return OUTBOUND_DATE
    context.user_data['outbound_date'] = date_text
    await update.message.reply_text("📅 Enter return date (YYYY-MM-DD):")
    return RETURN_DATE


async def return_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    if not validate_date(date_text):
        await update.message.reply_text("⚠️ Invalid date format. Please enter date as YYYY-MM-DD:")
        return RETURN_DATE
    context.user_data['return_date'] = date_text

    # Call the API only once when both dates are provided
    params = {
        "departure_id": CITY_TO_AIRPORT[context.user_data['departure_city']],
        "arrival_id": CITY_TO_AIRPORT[context.user_data['arrival_city']],
        "outbound_date": context.user_data['outbound_date'],
        "return_date": context.user_data['return_date']
    }
    insights = fetch_price_insights(params)

    # Check if flight data is available
    if not insights or 'lowest_price' not in insights:
        await update.message.reply_text(
            "⚠️ No available flights for the given dates. Restarting.\n\n🛫 Enter departure city (e.g., Manchester):"
        )
        return DEPARTURE

    formatted_output = format_price_insights(insights)
    await update.message.reply_text(formatted_output, parse_mode="Markdown")

    job_id = str(context.user_data['chat_id'])
    # Remove any existing job for this chat
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        send_daily_update,
        'interval',
        days=1,
        args=[context.user_data, context.bot],
        id=job_id
    )
    # Start the scheduler if not already running
    if not scheduler.running:
        scheduler.start()

    await update.message.reply_text(
        "✅ Daily updates scheduled! You will receive updates daily.\n"
        "Type 'Don't want more updates' or /stop to cancel and start a new schedule."
    )
    return ConversationHandler.END


def fetch_price_insights(params):
    search = GoogleSearch({"engine": "google_flights", "currency": "GBP",
                           "hl": "en", "stops": 1, "api_key": api_key, **params})
    return search.get_dict().get("price_insights", {})


def format_price_insights(insights):
    output = (
        f"✈️ *Flight Price Insights:*\n\n"
        f"Lowest Price: £{insights.get('lowest_price')}\n"
        f"Price Level: {insights.get('price_level').title()}\n"
        f"Typical Range: £{insights['typical_price_range'][0]} - £{insights['typical_price_range'][1]}\n\n"
        f"📅 *Price History:*\n"
    )
    for timestamp, price in reversed(insights.get('price_history', [])):
        date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
        output += f"- {date}: £{price}\n"
    return output


def validate_date(date_text):
    try:
        datetime.strptime(date_text, '%Y-%m-%d')
        return True
    except Exception:
        return False


async def send_daily_update(user_data, bot: Bot):
    params = {
        "departure_id": CITY_TO_AIRPORT[user_data['departure_city']],
        "arrival_id": CITY_TO_AIRPORT[user_data['arrival_city']],
        "outbound_date": user_data['outbound_date'],
        "return_date": user_data['return_date']
    }
    insights = fetch_price_insights(params)
    chat_id = user_data['chat_id']
    if not insights or 'lowest_price' not in insights:
        await bot.send_message(
            chat_id=chat_id,
            text="⚠️ The specified dates no longer have any available flights. Notifications cancelled. "
                 "Please enter a valid departure city to start a new schedule."
        )
        job_id = str(chat_id)
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)
    else:
        formatted_output = format_price_insights(insights)
        await bot.send_message(chat_id=chat_id, text=formatted_output, parse_mode="Markdown")


async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = str(update.message.chat_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        await update.message.reply_text(
            "🛑 Notifications cancelled. Please enter a new departure city to start a new schedule."
        )
    else:
        await update.message.reply_text(
            "No active notifications found. Please enter a new departure city to start a new schedule."
        )
    # Optionally, restart the conversation by calling the start prompt:
    return await start(update, context)


def main():
    app = ApplicationBuilder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            DEPARTURE: [MessageHandler(filters.TEXT, departure_city)],
            ARRIVAL: [MessageHandler(filters.TEXT, arrival_city)],
            OUTBOUND_DATE: [MessageHandler(filters.TEXT, outbound_date)],
            RETURN_DATE: [MessageHandler(filters.TEXT, return_date)]
        },
        fallbacks=[CommandHandler('stop', stop_notifications)]
    )
    app.add_handler(conv_handler)

    # Also handle text messages for cancellation (e.g., "Don't want more updates")
    app.add_handler(MessageHandler(
        filters.Regex("(?i)^(Don't want( to get)? more updates)$"),
        stop_notifications
    ))
    if not scheduler.running:  # Ensure it's started once
        scheduler.start()
    app.run_polling()


if __name__ == "__main__":
    main()
