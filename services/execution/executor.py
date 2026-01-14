"""
ZERO Execution Gateway - Alpaca Order Execution
PAPER ONLY - Hard enforced
"""

import os
import asyncio
from typing import Optional, Dict, Any, Tuple
from alpaca.trading.client import TradingClient
from alpaca.trading.requests import MarketOrderRequest, LimitOrderRequest
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.common.exceptions import APIError
import logging

logger = logging.getLogger(__name__)


class AlpacaExecutor:
    """Alpaca order execution (PAPER ONLY)"""
    
    def __init__(self):
        self.api_key = os.getenv('ALPACA_API_KEY')
        self.secret_key = os.getenv('ALPACA_SECRET_KEY')
        self.paper = os.getenv('ALPACA_PAPER', 'false').lower() == 'true'
        
        # HARD ENFORCEMENT: Must be paper mode
        if not self.paper:
            raise ValueError("❌ CRITICAL: ALPACA_PAPER must be 'true'. Execution service refuses to start in live mode.")
        
        if not self.api_key or not self.secret_key:
            raise ValueError("❌ CRITICAL: ALPACA_API_KEY and ALPACA_SECRET_KEY must be set.")
        
        # Initialize Alpaca client (PAPER mode)
        self.client = TradingClient(
            api_key=self.api_key,
            secret_key=self.secret_key,
            paper=True  # Hard code paper=True for safety
        )
        
        logger.info("✅ Alpaca executor initialized (PAPER MODE ONLY)")
    
    async def check_open_position(self, ticker: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """
        Check if there's an open position for this ticker
        Returns: (has_position, position_data)
        """
        try:
            # Run synchronous Alpaca call in thread pool
            positions = await asyncio.to_thread(self.client.get_all_positions)
            for pos in positions:
                if pos.symbol == ticker:
                    return True, {
                        'symbol': pos.symbol,
                        'qty': float(pos.qty),
                        'avg_entry_price': float(pos.avg_entry_price),
                        'market_value': float(pos.market_value)
                    }
            return False, None
        except Exception as e:
            logger.error(f"❌ Failed to check open positions: {e}")
            # Fail safe: assume position exists to prevent duplicate
            return True, None
    
    async def place_market_order(
        self,
        ticker: str,
        quantity: int = 1,
        side: OrderSide = OrderSide.BUY
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        Place a market order (PAPER ONLY)
        Returns: (order_id, error_message)
        """
        try:
            # Create market order request
            market_order_data = MarketOrderRequest(
                symbol=ticker,
                qty=quantity,
                side=side,
                time_in_force=TimeInForce.DAY
            )
            
            # Submit order (run in thread pool since Alpaca client is sync)
            market_order = await asyncio.to_thread(
                self.client.submit_order,
                order_data=market_order_data
            )
            order_id = str(market_order.id)
            
            logger.info(f"✅ Submitted market order for {ticker}: order_id={order_id}, qty={quantity}")
            return order_id, None
            
        except APIError as e:
            error_msg = f"Alpaca API error: {e}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
        except Exception as e:
            error_msg = f"Unexpected error placing order: {e}"
            logger.error(f"❌ {error_msg}")
            return None, error_msg
    
    async def get_account_info(self) -> Optional[Dict[str, Any]]:
        """Get account information"""
        try:
            account = await asyncio.to_thread(self.client.get_account)
            return {
                'buying_power': float(account.buying_power),
                'cash': float(account.cash),
                'portfolio_value': float(account.portfolio_value),
                'pattern_day_trader': account.pattern_day_trader,
                'trading_blocked': account.trading_blocked,
                'account_blocked': account.account_blocked
            }
        except Exception as e:
            logger.error(f"❌ Failed to get account info: {e}")
            return None
