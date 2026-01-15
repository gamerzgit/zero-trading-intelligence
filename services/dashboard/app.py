"""
ZERO Trading Intelligence Platform - Dashboard
Milestone 5: Real-time Command Center

Displays:
- Regime Status (Header): Market state (GREEN/YELLOW/RED)
- Brain (Main Table): Top opportunities
- Scanner (Sidebar): Active candidates
"""

import streamlit as st
import pandas as pd
import time
from datetime import datetime
from typing import Optional, Dict, Any
import sys
import os

# Add parent directory to path for contracts
project_root = os.path.join(os.path.dirname(__file__), '../../')
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from connection import RedisConnection

# Page config
st.set_page_config(
    page_title="ZERO Trading Intelligence",
    page_icon="🎯",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Initialize Redis connection
@st.cache_resource
def get_redis():
    """Get Redis connection (cached)"""
    return RedisConnection()

redis_conn = get_redis()

# Custom CSS for traffic light
st.markdown("""
<style>
    .traffic-light {
        display: inline-block;
        padding: 10px 20px;
        border-radius: 8px;
        font-weight: bold;
        font-size: 24px;
        text-align: center;
        margin: 10px 0;
    }
    .traffic-light.GREEN {
        background-color: #4CAF50;
        color: white;
    }
    .traffic-light.YELLOW {
        background-color: #FFC107;
        color: black;
    }
    .traffic-light.RED {
        background-color: #F44336;
        color: white;
    }
    .opportunity-high {
        background-color: #E8F5E9;
    }
    .opportunity-medium {
        background-color: #FFF9C4;
    }
    .opportunity-low {
        background-color: #FFEBEE;
    }
</style>
""", unsafe_allow_html=True)

def format_traffic_light(state: str) -> str:
    """Format traffic light HTML"""
    return f'<div class="traffic-light {state}">{state}</div>'

def get_market_state_display(market_state: Optional[Dict[str, Any]]) -> tuple:
    """Get market state display info"""
    if not market_state:
        return "UNKNOWN", "System Idle / Market Closed", None, None, None
    
    state = market_state.get('state', 'UNKNOWN')
    reason = market_state.get('reason', 'No reason provided')
    vix_level = market_state.get('vix_level')  # Real VIX (may be None)
    vixy_price = market_state.get('vixy_price')  # VIXY ETF price
    timestamp = market_state.get('timestamp')
    
    return state, reason, vix_level, vixy_price, timestamp

def format_opportunities_table(opportunity_rank: Optional[Dict[str, Any]]) -> pd.DataFrame:
    """Format opportunities as DataFrame"""
    if not opportunity_rank or 'opportunities' not in opportunity_rank:
        return pd.DataFrame()
    
    opportunities = opportunity_rank.get('opportunities', [])
    if not opportunities:
        return pd.DataFrame()
    
    rows = []
    for opp in opportunities:
        # Format why as string
        why_list = opp.get('why', [])
        why_str = ' | '.join(why_list) if why_list else 'N/A'
        
        rows.append({
            'Ticker': opp.get('ticker', 'N/A'),
            'Probability %': f"{opp.get('probability', 0) * 100:.2f}%",
            'Score': f"{opp.get('opportunity_score', 0):.2f}",
            'Horizon': opp.get('horizon', 'N/A'),
            'Why': why_str[:100] + '...' if len(why_str) > 100 else why_str,
            'Target ATR': f"{opp.get('target_atr', 0):.2f}",
            'Stop ATR': f"{opp.get('stop_atr', 0):.2f}",
            'Market State': opp.get('market_state', 'N/A'),
        })
    
    return pd.DataFrame(rows)

def get_candidates_list(active_candidates: Optional[Dict[str, Any]]) -> list:
    """Get candidates list for sidebar"""
    if not active_candidates or 'candidates' not in active_candidates:
        return []
    
    return active_candidates.get('candidates', [])

# Main app
def main():
    """Main dashboard application"""
    
    # Header
    st.title("🎯 ZERO Trading Intelligence Platform")
    st.markdown("---")
    
    # Auto-refresh control
    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        auto_refresh = st.checkbox("Auto-Refresh", value=True)
    with col2:
        refresh_interval = st.selectbox("Interval (sec)", [2, 3, 5, 10], index=1)
    
    # Check Redis connection
    if not redis_conn.is_connected():
        st.error("❌ Cannot connect to Redis. Please check if Redis is running.")
        st.stop()
    
    # Fetch data
    market_state = redis_conn.get_market_state()
    opportunity_rank = redis_conn.get_opportunity_rank()
    active_candidates = redis_conn.get_active_candidates()
    
    # Sidebar - Scanner
    with st.sidebar:
        st.header("🔍 Scanner")
        candidates = get_candidates_list(active_candidates)
        
        if candidates:
            st.write(f"**Active Candidates:** {len(candidates)}")
            for ticker in candidates:
                st.write(f"- {ticker}")
            
            if active_candidates:
                horizon = active_candidates.get('horizon', 'N/A')
                scan_time = active_candidates.get('scan_time', 'N/A')
                st.caption(f"Horizon: {horizon}")
                st.caption(f"Scan Time: {scan_time}")
        else:
            st.info("No active candidates")
            if active_candidates:
                st.caption("Scanner may be idle or market closed")
    
    # Main content area
    # Regime Status (Header)
    st.header("🚦 Regime Status")
    
    state, reason, vix_level, vixy_price, timestamp = get_market_state_display(market_state)
    
    col1, col2 = st.columns([2, 3])
    
    with col1:
        st.markdown(format_traffic_light(state), unsafe_allow_html=True)
        # Display VIX level if available, otherwise show VIXY price
        if vix_level is not None:
            st.metric("VIX Level", f"{vix_level:.2f}")
        elif vixy_price is not None:
            st.metric("VIXY Price", f"${vixy_price:.2f}", help="VIXY ETF price (volatility proxy, NOT VIX)")
    
    with col2:
        st.write(f"**Reason:** {reason}")
        if timestamp:
            try:
                ts = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                st.caption(f"Last Updated: {ts.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            except:
                st.caption(f"Last Updated: {timestamp}")
    
    st.markdown("---")
    
    # Brain (Main Table) - Opportunities
    st.header("🧠 Brain - Top Opportunities")
    
    df = format_opportunities_table(opportunity_rank)
    
    if not df.empty:
        # Highlight high-probability rows
        def highlight_probability(row):
            prob_pct = float(row['Probability %'].replace('%', ''))
            if prob_pct >= 50:
                return ['background-color: #E8F5E9'] * len(row)
            elif prob_pct >= 30:
                return ['background-color: #FFF9C4'] * len(row)
            else:
                return ['background-color: #FFEBEE'] * len(row)
        
        st.dataframe(
            df.style.apply(highlight_probability, axis=1),
            use_container_width=True,
            hide_index=True
        )
        
        # Show metadata
        if opportunity_rank:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Opportunities", len(df))
            with col2:
                horizon = opportunity_rank.get('horizon', 'N/A')
                st.metric("Horizon", horizon)
            with col3:
                total_candidates = opportunity_rank.get('total_candidates', 0)
                st.metric("Total Candidates", total_candidates)
    else:
        st.info("No opportunities available. System may be idle or market closed.")
        if opportunity_rank:
            st.caption("Opportunity rank exists but is empty")
    
    # Footer
    st.markdown("---")
    st.caption(f"Last Refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main()
