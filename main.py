import os
from dotenv import load_dotenv
from serpapi import GoogleSearch
from datetime import datetime
from telegram import Update, Bot
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    ConversationHandler, MessageHandler, filters
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import timedelta

load_dotenv()
api_key = os.getenv("SERPAPI_API_KEY")
bot_token = os.getenv("TELEGRAM_BOT_TOKEN")

CITY_TO_AIRPORT = {
    "Manchester": "MAN", "Sevilla": "SVQ", "Gdansk": "GDN",
    "Malaga": "AGP", "Faro": "FAO", "London": "LHR", "Japan": "TYO"
}

scheduler = AsyncIOScheduler()

DEPARTURE, ARRIVAL, OUTBOUND_DATE, RETURN_DATE = range(4)

# Start command handler


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Save chat_id dynamically
    context.user_data['chat_id'] = update.message.chat_id
    await update.message.reply_text("🛫 Enter departure city (e.g., Manchester):")
    return DEPARTURE


# async def departure_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     context.user_data['departure_city'] = update.message.text
#     await update.message.reply_text("🏙️ Enter arrival city (e.g., Sevilla):")
#     return ARRIVAL
#
#
# async def arrival_city(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     context.user_data['arrival_city'] = update.message.text
#     await update.message.reply_text("📅 Enter departure date (YYYY-MM-DD):")
#     return OUTBOUND_DATE
#
#
# async def outbound_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     context.user_data['outbound_date'] = update.message.text
#     await update.message.reply_text("📅 Enter return date (YYYY-MM-DD):")
#     return RETURN_DATE


def fetch_alternative_dates(user_data):
    departure_date = datetime.strptime(user_data['outbound_date'], '%Y-%m-%d')
    alternatives = []

    for delta_days in range(-7, 8):
        alt_departure = departure_date + timedelta(days=delta_days)
        alt_return = alt_departure + timedelta(days=7)  # assuming 7-day trip

        params = {
            "engine": "google_flights",
            "currency": "GBP",
            "hl": "en",
            "stops": 1,
            "api_key": api_key,
            "departure_id": CITY_TO_AIRPORT[user_data['departure_city']],
            "arrival_id": CITY_TO_AIRPORT[user_data['arrival_city']],
            "outbound_date": alt_departure.strftime('%Y-%m-%d'),
            "return_date": alt_return.strftime('%Y-%m-%d')
        }

        insights = fetch_price_insights(params)
        if insights and 'lowest_price' in insights:
            alternatives.append(
                f"- Depart: {alt_departure.strftime('%Y-%m-%d')}, Return: {alt_return.strftime('%Y-%m-%d')}, Price: £{insights['lowest_price']}"
            )

    return alternatives


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


# async def return_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
#     context.user_data['return_date'] = update.message.text
#     insights = fetch_price_insights({
#         "departure_id": CITY_TO_AIRPORT[context.user_data['departure_city'].title()],
#         "arrival_id": CITY_TO_AIRPORT[context.user_data['arrival_city'].title()],
#         "outbound_date": context.user_data['outbound_date'],
#         "return_date": context.user_data['return_date']
#     })
#     formatted_output = format_price_insights(insights)
#     await update.message.reply_text(formatted_output, parse_mode="Markdown")
#
#     # Remove existing job if present to avoid duplicates
#     if scheduler.get_job(str(context.user_data['chat_id'])):
#         scheduler.remove_job(str(context.user_data['chat_id']))
#
#     # Schedule daily updates
#     scheduler.add_job(
#         send_daily_update,
#         'interval',
#         days=1,
#         args=[context.user_data, context.bot],
#         id=str(context.user_data['chat_id'])
#     )
#     scheduler.start()
#
#     await update.message.reply_text("✅ Daily updates scheduled! Type /stop to cancel.")
#     return ConversationHandler.END

async def return_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_text = update.message.text.strip()
    if not validate_date(date_text):
        await update.message.reply_text("⚠️ Invalid date format. Please enter date as YYYY-MM-DD:")
        return RETURN_DATE
    context.user_data['return_date'] = date_text

    insights = fetch_price_insights({
        "departure_id": CITY_TO_AIRPORT[context.user_data['departure_city']],
        "arrival_id": CITY_TO_AIRPORT[context.user_data['arrival_city']],
        "outbound_date": context.user_data['outbound_date'],
        "return_date": context.user_data['return_date']
    })

    if not insights or 'lowest_price' not in insights:
        available_alternatives = fetch_alternative_dates(context.user_data)
        if available_alternatives:
            formatted_alternatives = '\n'.join(available_alternatives)
            await update.message.reply_text(
                f"⚠️ No flights found for dates {context.user_data['outbound_date']} - {context.user_data['return_date']}.\n\n"
                f"✅ *Available alternatives:*\n{formatted_alternatives}\n\n"
                "Please enter a new departure date (YYYY-MM-DD):",
                parse_mode="Markdown"
            )
        else:
            await update.message.reply_text(
                "⚠️ No available flights found within ±7 days. Try different cities or dates."
            )
        return OUTBOUND_DATE  # Re-prompt user

    formatted_output = format_price_insights(insights)
    await update.message.reply_text(formatted_output, parse_mode="Markdown")

    job_id = str(context.user_data['chat_id'])
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    scheduler.add_job(
        send_daily_update,
        'interval',
        days=1,
        args=[context.user_data, context.bot],
        id=job_id
    )
    scheduler.start()

    await update.message.reply_text("✅ Daily updates scheduled! Type /stop to cancel.")
    return ConversationHandler.END

# Fetch flight price insights


def fetch_price_insights(params):
    search_params = {
        "engine": "google_flights", "currency": "GBP",
        "hl": "en", "stops": 2, "api_key": api_key, **params
    }
    search = GoogleSearch(search_params)
    results = search.get_dict()
    return results.get("price_insights", {})

# Format insights into readable message


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

# Send daily updates


async def send_daily_update(user_data, bot: Bot):
    insights = fetch_price_insights({
        "departure_id": CITY_TO_AIRPORT[user_data['departure_city'].title()],
        "arrival_id": CITY_TO_AIRPORT[user_data['arrival_city'].title()],
        "outbound_date": user_data['outbound_date'],
        "return_date": user_data['return_date']
    })
    formatted_output = format_price_insights(insights)
    await bot.send_message(chat_id=user_data['chat_id'], text=formatted_output, parse_mode="Markdown")

# Stop command to cancel daily notifications


async def stop_notifications(update: Update, context: ContextTypes.DEFAULT_TYPE):
    job_id = str(update.message.chat_id)
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        await update.message.reply_text("🛑 Daily notifications cancelled.")
    else:
        await update.message.reply_text("⚠️ No active notifications to cancel.")

# Main function to start bot


def main():
    app = ApplicationBuilder().token(bot_token).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            DEPARTURE: [MessageHandler(filters.TEXT, departure_city)],
            ARRIVAL: [MessageHandler(filters.TEXT, arrival_city)],
            OUTBOUND_DATE: [MessageHandler(filters.TEXT, outbound_date)],
            RETURN_DATE: [MessageHandler(filters.TEXT, return_date)],
        },
        fallbacks=[]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler('stop', stop_notifications))

    print("🚀 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
