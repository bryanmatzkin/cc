#!/bin/bash
set -e

echo "=== Kalshi AI Trading Bot - Railway Startup ==="

# Decode the Kalshi private key from base64 env variable and write to file
if [ -n "$KALSHI_PRIVATE_KEY_BASE64" ]; then
  echo "$KALSHI_PRIVATE_KEY_BASE64" | base64 -d > kalshi_private_key.pem
    chmod 600 kalshi_private_key.pem
      echo "Private key written from KALSHI_PRIVATE_KEY_BASE64 env variable."
      else
        echo "ERROR: KALSHI_PRIVATE_KEY_BASE64 is not set!"
          echo "Please add your base64-encoded Kalshi private key as an environment variable."
            echo "Generate it with: base64 -w 0 < your_kalshi_private_key.pem"
              exit 1
              fi

              # Initialize database
              echo "Initializing database..."
              python -m src.utils.database

              # Determine trading mode from env variable (default: paper)
              TRADING_MODE="${TRADING_MODE:-paper}"
              echo "Starting bot in $TRADING_MODE mode..."

              if [ "$TRADING_MODE" = "live" ]; then
                python cli.py run --live
                elif [ "$TRADING_MODE" = "safe-compounder" ]; then
                  python cli.py run --safe-compounder --live
                  elif [ "$TRADING_MODE" = "safe-compounder-paper" ]; then
                    python cli.py run --safe-compounder
                    elif [ "$TRADING_MODE" = "disciplined" ]; then
                      python cli.py run --disciplined --live
                      else
                        python cli.py run --paper
                        fi
