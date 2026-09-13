import streamlit as st

from matching import MatchingEngine, Side


if "engine" not in st.session_state:
    st.session_state.engine = MatchingEngine()

engine = st.session_state.engine

st.title("Order Book Demo")

side_name = st.selectbox("Side", ["BID", "ASK"])
price = st.number_input("Price", value=100.00, step=0.01)
quantity = st.number_input("Quantity", value=10, min_value=1)

if st.button("Place Limit Order"):
    side = Side.BID if side_name == "BID" else Side.ASK

    report = engine.place_limit(
        side,
        price,
        quantity
    )

    st.subheader("Execution Report")

    st.write("Order ID:", report.order_id)
    st.write("Status:", report.status.value)
    st.write("Filled Quantity:", report.filled_qty)
    st.write("Open Quantity:", report.open_qty)
    st.write("Resting Price:", report.resting_price)


st.subheader("Order Book")

col1, col2 = st.columns(2)

with col1:
    st.write("### BIDS")

    bids = engine.ladder(Side.BID)

    if bids:
        st.table({
            "Price": [price for price, depth in bids],
            "Quantity": [depth for price, depth in bids],
        })
    else:
        st.write("No bids")


with col2:
    st.write("### ASKS")

    asks = engine.ladder(Side.ASK)

    if asks:
        st.table({
            "Price": [price for price, depth in asks],
            "Quantity": [depth for price, depth in asks],
        })
    else:
        st.write("No asks")


st.subheader("Market")

st.write("Best Bid:", engine.best_bid())
st.write("Best Ask:", engine.best_ask())
st.write("Spread:", engine.spread())
st.write("Mid:", engine.mid())