# Pokémon 30th collection availability monitor

Czech shop product monitoring, price strictly below CZK 4,000 excluding shipping, including in-stock products and preorders. Sends Telegram alerts for new eligible offers, restocks, price drops and preorder-to-stock transitions.

## Deployment status

NOT YET LIVE. Runs are validation-only until repository variable `WATCH_ENABLED` is `true`. Configure repository Actions secrets `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`, verify adapters and Telegram delivery before enabling. Do not put credentials in files, commits or issues. The chat ID identifies the recipient, not the bot.

Standard public GitHub Actions runners are used. Schedule: every 15 minutes at minutes 7,22,37,52; GitHub may delay/drop scheduled jobs and may disable schedules after inactivity. This is not an exact-timing service. No paid services are enabled.

## Coverage and limitations

The configured product URLs and collection pages are monitored. Collection links on the same shop hostname are discovered each run. This does NOT search the whole web or automatically discover new retailers. The first 250 discovered URLs are scanned. A supported page must expose unambiguous Product JSON-LD with a CZK price and availability. JavaScript-only pages, blocks and missing metadata need shop-specific adapters. Failed scans preserve previous observations and are listed in the run summary. Product data may lag visible stock: check the shop before purchase. VAT and product variant must be checked during adapter validation.

Preorders are labeled separately. Release dates are not yet extracted. No automated purchases. Notification failures retry next run; a crash between delivery and saving state may create a duplicate. Public `state.json` contains only product URLs, prices and availability — no credentials or chat IDs. Review GitHub Actions failures regularly; there is no independent outage monitor yet.

Run local logic tests: `python3 -m unittest -v`. Run validation scan: `python3 runner.py` with WATCH_ENABLED unset. Python standard library only.

Sources: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows and https://core.telegram.org/bots/api
