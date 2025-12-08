import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

import streamlit as st
import sqlite3
import pandas as pd
import plotly.graph_objects as go

# Page configuration
st.set_page_config(page_title="Product Recommendation Dashboard", layout="wide")

# Database connection
@st.cache_resource
def get_connection():
    return sqlite3.connect('product_apriori_senti.db', check_same_thread=False)

conn = get_connection()

# not to include in product
no_product = ('Fruits', 'Jams, Jellies & Sweet Spreads', 'Jams, Jellies & Preserves', 'Processed', 'Red', 'White', 'Brown')

# Load data
@st.cache_data
def load_products():
    query = f"SELECT DISTINCT item_id, item FROM product WHERE item NOT IN {no_product} ORDER BY item"
    return pd.read_sql(query, conn)

@st.cache_data
def load_top_products():
    return pd.read_sql("SELECT * FROM top_products", conn)

@st.cache_data
def load_market_basket():
    return pd.read_sql("SELECT * FROM market_basket", conn)

# Load all data
df_products = load_products()
df_top_products = load_top_products()
df_market_basket = load_market_basket()

# Create item to item_id mapping
item_to_id = dict(zip(df_products['item'], df_products['item_id']))
id_to_item = dict(zip(df_products['item_id'], df_products['item']))

# App Title
st.title("🛒 Product Recommendation Dashboard")

# Layout: Two columns
col_left, col_right = st.columns([1, 2])

# ============================================
# LEFT COLUMN
# ============================================
with col_left:
    st.header("Product Selection")
    
    # Product selector
    selected_product = st.selectbox(
        "Select a Product:",
        options=df_products['item'].tolist(),
        index=0
    )
    
    selected_item_id = item_to_id[selected_product]
    st.info(f"**Selected Product ID:** {selected_item_id}")
    
    st.markdown("---")
    
    # Top Products Section - Show rank 1-3 products for selected item_id ONLY (one per rank)
    st.subheader("📊 Top Ranked Products")
    
    if not df_top_products.empty:
        # Filter for selected item_id AND rank between 1-3
        selected_products = df_top_products[
            (df_top_products['item_id'] == selected_item_id) & 
            (df_top_products['rank'].between(1, 3))
        ].sort_values('rank')
        
        # Remove duplicate ranks - keep only the first occurrence of each rank
        selected_products = selected_products.drop_duplicates(subset=['rank'], keep='first')
        
        if not selected_products.empty:
            for idx, row in selected_products.iterrows():
                with st.container():
                    st.markdown(f"**Rank {int(row.get('rank', 0))}: {row.get('title', 'N/A')}**")
                    price = row.get('price')
                    if pd.notna(price):
                        st.write(f"💰 Price: ${float(price):.2f}")
                    else:
                        st.write("💰 Price: N/A")
                    st.write(f"⭐ Rating: {row.get('average_rating', 0):.1f}")
                    st.markdown("---")
        else:
            st.warning(f"No top-ranked products (rank 1-3) found for {selected_product}")
    else:
        st.warning("No product details available")

# ============================================
# RIGHT COLUMN
# ============================================
with col_right:
    st.header(f"Recommendations for: {selected_product}")
    
    # Filter market basket for selected product
    # Convert antecedents_id to match selected_item_id
    df_recommendations = df_market_basket.copy()
    
    # Filter rows where selected_item_id is in antecedents_id
    df_recommendations['antecedents_id_list'] = df_recommendations['antecedents_id'].astype(str).str.split(', ')
    df_recommendations = df_recommendations[
        df_recommendations['antecedents_id_list'].apply(
            lambda x: str(selected_item_id) in x if isinstance(x, list) else False
        )
    ]
    
    # Filter by lift > 1.0
    df_recommendations = df_recommendations[df_recommendations['lift'] > 1.0]
    
    if not df_recommendations.empty:
        # Sort by lift in descending order
        df_recommendations = df_recommendations.sort_values('lift', ascending=False)
        
        st.success(f"Found {len(df_recommendations)} product recommendations with lift > 1.0")
        
        # Create visualization data
        viz_data = []
        for idx, row in df_recommendations.iterrows():
            consequent_ids = str(row['consequents_id']).split(', ')
            consequent_names = row['consequents']
            
            for cons_id in consequent_ids:
                if cons_id and cons_id != 'None':
                    cons_item = id_to_item.get(int(cons_id), consequent_names)
                    viz_data.append({
                        'Product': cons_item,
                        'Lift': row['lift'],
                        'Confidence': row['confidence'],
                        'Support': row['support']
                    })
        
        if viz_data:
            df_viz = pd.DataFrame(viz_data)
            df_viz = df_viz.sort_values('Lift', ascending=True)
            
            # Horizontal Bar Chart
            fig = go.Figure()
            
            fig.add_trace(go.Bar(
                y=df_viz['Product'],
                x=df_viz['Lift'],
                orientation='h',
                marker=dict(
                    color=df_viz['Lift'],
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title="Lift")
                ),
                text=df_viz['Lift'].round(2),
                textposition='auto',
                hovertemplate='<b>%{y}</b><br>' +
                              'Lift: %{x:.2f}<br>' +
                              'Confidence: %{customdata[0]:.2f}<br>' +
                              'Support: %{customdata[1]:.3f}<br>' +
                              '<extra></extra>',
                customdata=df_viz[['Confidence', 'Support']].values
            ))
            
            fig.update_layout(
                title=f"Products to Buy with '{selected_product}' (Lift > 1.0)",
                xaxis_title="Lift Score",
                yaxis_title="Recommended Products",
                height=max(400, len(df_viz) * 30),
                showlegend=False,
                hovermode='closest'
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # Display detailed table
            st.subheader("📋 Detailed Recommendations")
            df_display = df_viz.sort_values('Lift', ascending=False)
            df_display['Lift'] = df_display['Lift'].round(2)
            df_display['Confidence'] = df_display['Confidence'].round(2)
            df_display['Support'] = df_display['Support'].round(3)
            st.dataframe(df_display, use_container_width=True, hide_index=True)
        else:
            st.warning("Could not map consequent IDs to product names")
    else:
        st.warning(f"No recommendations found for '{selected_product}' with lift > 1.0")
        st.info("Try selecting a different product or lowering the lift threshold")

# Footer
st.markdown("---")
st.caption("Product Recommendation Dashboard | Powered by Apriori Algorithm & Market Basket Analysis")