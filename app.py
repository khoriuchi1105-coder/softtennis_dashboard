import streamlit as st
import pandas as pd
import os
import plotly.express as px
import gspread
from oauth2client.service_account import ServiceAccountCredentials

st.set_page_config(page_title="ソフトテニス部 ダッシュボード", layout="wide")

def check_password():
    """Returns `True` if the user had the correct password."""
    def password_entered():
        # Check against the password stored in secrets.toml
        if st.session_state["password"] == st.secrets.get("password", "nssu2026"):
            st.session_state["password_correct"] = True
            del st.session_state["password"]  # don't store password
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("閲覧用パスワードを入力してください", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("閲覧用パスワードを入力してください", type="password", on_change=password_entered, key="password")
        st.error("😕 パスワードが間違っています")
        return False
    return True

if not check_password():
    st.stop()

st.title("🎾 ソフトテニス部 体力測定ダッシュボード")
st.markdown("体力測定結果の推移と、チーム全体でのグループ比較を確認できます。\n**Googleスプレッドシート** に入力されたデータがオンラインで自動反映されます。")

@st.cache_data(ttl=600)
def load_unified_data_from_gs():
    """スプレッドシートから時期別（シート別）のデータを読み込む"""
    fitness_data = {}
    try:
        gcp_creds = dict(st.secrets["gcp_service_account"])
        gcp_creds["private_key"] = gcp_creds["private_key"].replace('\\n', '\n')
        
        credentials = ServiceAccountCredentials.from_json_keyfile_dict(
            gcp_creds, 
            ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
        )
        client = gspread.authorize(credentials)
        
        spreadsheet_url = st.secrets["spreadsheet"]["url"]
        spreadsheet = client.open_by_url(spreadsheet_url)
        
        for worksheet in spreadsheet.worksheets():
            sheet_name = worksheet.title
            records = worksheet.get_all_values()
            if len(records) > 1:
                headers = records[0]
                df = pd.DataFrame(records[1:], columns=headers)
                df = df.replace(r'^\s*$', pd.NA, regex=True)
                fitness_data[sheet_name] = df
                
        return fitness_data
    except Exception as e:
        st.error(f"スプレッドシート読み込みエラー: {e}")
        return {}

@st.cache_data
def load_inbody_data():
    filepath = os.path.join(os.path.dirname(os.path.abspath(__file__)), "日体大女子2026inbody.xlsx")
    if not os.path.exists(filepath):
        return pd.DataFrame()
    try:
        df_raw = pd.read_excel(filepath, sheet_name=0, header=None)
        names_row = df_raw.iloc[1].tolist()
        col_end = names_row.index('平均') if '平均' in names_row else len(names_row)
        df_data = df_raw.iloc[2:].copy()
        cols = list(names_row)
        cols[0] = '指標'
        cols[1] = '測定日'
        df_data.columns = cols
        df_data['指標'] = df_data['指標'].ffill()
        df_data = df_data.dropna(subset=['測定日'])
        athlete_cols = [col for col in cols[2:col_end] if pd.notna(col) and str(col).strip() != '']
        df_data = df_data.loc[:, ~df_data.columns.duplicated()]
        melted = pd.melt(df_data, id_vars=['指標', '測定日'], value_vars=athlete_cols, var_name='氏名', value_name='値')
        melted = melted.dropna(subset=['値'])
        melted['値'] = pd.to_numeric(melted['値'], errors='coerce')
        return melted.dropna(subset=['値'])
    except Exception as e:
        st.error(f"InBodyファイルの読み込みエラー: {e}")
        return pd.DataFrame()

# -----------------------------------------------------------------------------
# Data Initialization
# -----------------------------------------------------------------------------
with st.spinner("クラウドからデータを取得しています..."):
    fitness_data_dict = load_unified_data_from_gs()
    inbody_df = load_inbody_data()

# サイドバーの学年フィルタ用（「現在の学年」とするため、一番最後に作成されたシート（最新）を基準にする）
latest_sheet = list(fitness_data_dict.keys())[-1] if fitness_data_dict else None

if latest_sheet:
    players_df = fitness_data_dict[latest_sheet][['氏名', '学年']].dropna(subset=['氏名']).copy()
    players_df['学年'] = players_df['学年'].fillna('OG/その他').astype(str)
else:
    players_df = pd.DataFrame(columns=['氏名', '学年'])

if players_df.empty:
    st.warning("選手データが見つかりません。")
    st.stop()

# -----------------------------------------------------------------------------
# Sidebar Configuration
# -----------------------------------------------------------------------------
st.sidebar.header("⚙️ 表示設定")

# さわやかテイストのCSSと印刷(PDF)用設定
st.markdown("""
    <style>
    .stApp { background-color: #f4f8f9; }
    h1, h2, h3 { color: #1a5276; }
    </style>
""", unsafe_allow_html=True)
theme_template = 'plotly_white'
bar_color = '#2E86C1'

st.sidebar.markdown("---")
view_mode = st.sidebar.radio("表示モードを選択", [
    "個人詳細 (各選手のページ)", 
    "グループ比較 (学年別リスト・ソート)", 
    "チーム全体の推移 (時系列)",
    "【InBody】個人推移",
    "【InBody】グループ比較"
])

if view_mode == "個人詳細 (各選手のページ)":
    st.sidebar.subheader("絞り込み")
    available_grades = ["すべて"] + sorted(players_df['学年'].unique().tolist())
    
    # ユーザーが指定した学年フィルタ（最新シートの学年に基づく）
    selected_grade = st.sidebar.selectbox("現在の学年フィルタ", available_grades)
    
    if selected_grade != "すべて":
        filtered_players = players_df[players_df['学年'] == selected_grade]['氏名'].tolist()
    else:
        filtered_players = players_df['氏名'].tolist()
        
    if not filtered_players:
        st.warning("条件に一致する選手がいません。")
        st.stop()
        
    selected_player = st.selectbox("👤 選手を選択してください", filtered_players)
    st.divider()

    # --- 体力測定 ---
    st.header(f"🏃 {selected_player} 選手の体力測定 結果")
    if fitness_data_dict:
        # 最新シートの列情報からテスト項目を特定
        test_items = [c for c in fitness_data_dict[latest_sheet].columns if c not in ['ID', '氏名', '学年']]
        
        # 選手のごとに（全シートにわたる）時系列データを収集
        # 本人が過去に別の学年であっても、氏名が一貫していればデータが紐付きます
        player_scores = {test: {} for test in test_items}
        for season, df in fitness_data_dict.items():
            player_row = df[df['氏名'].astype(str).str.contains(selected_player, na=False)]
            if not player_row.empty:
                for test in test_items:
                    # シートによってカラム名がない場合は無視
                    if test in player_row.columns:
                        val = player_row.iloc[0].get(test)
                        player_scores[test][season] = pd.to_numeric(val, errors='coerce') if pd.notna(val) else None

        st.markdown("---")
        import plotly.graph_objects as go
        
        # --- グラフのグループ化定義 ---
        group_speed = ['10m走', '505テスト']
        group_med = ['メディシンボール投げ（フロントアンダー）', 'メディシンボール投げ（フロントオーバー）', 'メディシンボール投げ（バック）']
        group_stroke = [
            'ボールスピードMax（フォア）', 'ボールスピードAve（フォア）',
            'ボールスピードMax（バック）', 'ボールスピードAve（バック）',
            'ボールスピードMax（スマッシュ）', 'ボールスピードAve（スマッシュ）'
        ]
        group_cmj = ['CMJ（腕振りなし）', 'CMJ（腕振りあり）']
        group_yoyo = ['Yo-Yoテスト']
        
        plotted_tests = set()

        def plot_group(fig_title, items, format_str="{:.1f}"):
            fig = go.Figure()
            has_data = False
            for item in items:
                series = pd.Series(player_scores.get(item, {})).dropna()
                if not series.empty:
                    has_data = True
                    fig.add_trace(go.Scatter(
                        x=series.index.astype(str), y=series.values,
                        mode='lines+markers+text', name=item,
                        text=series.apply(lambda x: format_str.format(float(x)) if pd.notna(x) else ""),
                        textposition="top center"
                    ))
                    plotted_tests.add(item)
            if has_data:
                fig.update_layout(
                    title=fig_title, template=theme_template, hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=-0.3, xanchor="center", x=0.5),
                    height=280, margin=dict(l=10, r=10, t=30, b=10)
                )
                return fig
            return None

        # ==========================================
        # 1. パフォーマンス分析 部門
        # ==========================================
        st.subheader("🔥 パフォーマンス分析")
        col_p1, col_p2 = st.columns(2)
        
        p_figs = [
            plot_group("💨 アジリティ (10m / 505)", group_speed, format_str="{:.3f}"),
            plot_group("🥎 メディシン投げ", group_med),
            plot_group("🎾 ボールスピード", group_stroke),
            plot_group("🏃 Yo-Yo テスト", group_yoyo)
        ]
        p_figs = [f for f in p_figs if f is not None]
        for i, f in enumerate(p_figs):
            with [col_p1, col_p2][i % 2]:
                st.plotly_chart(f, use_container_width=True)

        st.markdown("---")
        
        # ==========================================
        # 2. トレーニング部門 (その他)
        # ==========================================
        st.subheader("💪 トレーニング部門")
        col_t1, col_t2 = st.columns(2)
        t_idx = 0
        
        fig_cmj = plot_group("🦘 CMJ (腕振りあり/なし)", group_cmj)
        if fig_cmj:
            with [col_t1, col_t2][t_idx % 2]:
                st.plotly_chart(fig_cmj, use_container_width=True)
            t_idx += 1

        for test in test_items:
            if test not in plotted_tests:
                series = pd.Series(player_scores.get(test, {})).dropna()
                if not series.empty:
                    fig_fit = px.line(
                        x=series.index.astype(str), y=series.values,
                        labels={'x': '測定時期', 'y': '記録'},
                        title=f"📈 {test}",
                        markers=True, 
                        text=series.apply(lambda x: f"{float(x):.1f}" if pd.notna(x) else ""), 
                        template=theme_template,
                        height=280
                    )
                    fig_fit.update_layout(margin=dict(l=10, r=10, t=30, b=10))
                    fig_fit.update_traces(line_color=bar_color, marker_color=bar_color, textposition='top center')
                    with [col_t1, col_t2][t_idx % 2]:
                        st.plotly_chart(fig_fit, use_container_width=True)
                    t_idx += 1
    else:
        st.warning("体力測定データが取得できませんでした。")

# =============================================================================
# InBody UI Logic
# =============================================================================
elif view_mode == "【InBody】個人推移":
    st.header("💪 【InBody】個人推移")
    if inbody_df.empty:
        st.warning("InBodyデータが読み込めません。`日体大女子2026inbody.xlsx` を確認してください。")
    else:
        players = sorted(inbody_df['氏名'].unique().tolist())
        selected_player = st.sidebar.selectbox("👤 選手を選択してください", players)
        
        st.subheader(f"{selected_player} 選手のInBody推移")
        player_inbody = inbody_df[inbody_df['氏名'] == selected_player]
        
        metrics = player_inbody['指標'].unique()
        selected_metrics = st.multiselect("表示する指標を選択", metrics, default=[m for m in ['体重 (kg)', '骨格筋量 (kg)', '体脂肪率 (%)'] if m in metrics])
        
        if selected_metrics:
            for metric in selected_metrics:
                plot_data = player_inbody[player_inbody['指標'] == metric]
                fig = px.line(
                    plot_data, x='測定日', y='値',
                    title=f"📈 {metric}", markers=True, text=plot_data['値'].apply(lambda x: f"{float(x):.1f}"),
                    template=theme_template, height=300
                )
                fig.update_traces(line_color='#27AE60', marker_color='#27AE60', textposition='top center')
                st.plotly_chart(fig, use_container_width=True)

elif view_mode == "【InBody】グループ比較":
    st.header("📊 【InBody】グループ比較")
    if inbody_df.empty:
        st.warning("InBodyデータが読み込めません。")
    else:
        dates = inbody_df['測定日'].unique().tolist()
        metrics = inbody_df['指標'].unique().tolist()
        
        col1, col2 = st.columns(2)
        target_date = col1.selectbox("比較する測定時期", dates, index=len(dates)-1)
        target_metric = col2.selectbox("比較する指標", metrics, index=metrics.index('骨格筋量 (kg)') if '骨格筋量 (kg)' in metrics else 0)
        
        date_df = inbody_df[(inbody_df['測定日'] == target_date) & (inbody_df['指標'] == target_metric)].copy()
        
        if not date_df.empty:
            date_df = date_df.sort_values(by='値', ascending=False).reset_index(drop=True)
            
            fig = px.bar(
                date_df, x='氏名', y='値', text=date_df['値'].apply(lambda x: f"{float(x):.1f}"),
                title=f"{target_date} - {target_metric} ランキング",
                template=theme_template
            )
            fig.update_traces(marker_color='#27AE60', textposition='outside')
            st.plotly_chart(fig, use_container_width=True)
            
            st.dataframe(date_df[['氏名', '値']].rename(columns={'値': target_metric}), hide_index=True)
        else:
            st.info("指定された条件のデータがありません。")

elif view_mode == "グループ比較 (学年別リスト・ソート)":
    st.header("👥 グループ比較・ソート機能")
    st.markdown("学年ごとに選手一覧を表示し、体力測定の各種テスト結果をソート・比較できます。")
    
    if not fitness_data_dict:
        st.warning("体力測定データが読み込めません。")
        st.stop()
        
    target_season = st.selectbox("比較する対象時期を選択", list(fitness_data_dict.keys()), index=len(fitness_data_dict.keys())-1)
    df_season = fitness_data_dict[target_season].copy()
    df_season['学年'] = df_season['学年'].fillna('OG/その他').astype(str)
    
    available_grades = sorted(df_season['学年'].unique().tolist())
    # データ内に存在する学年のみをデフォルト値に設定
    default_grades = [g for g in ["4年", "3年", "2年"] if g in available_grades]
    
    target_grades = st.multiselect("比較する学年を選択", available_grades, default=default_grades)
    
    if not target_grades:
        st.info("比較する学年を選択してください。")
        st.stop()
        
    filtered_df = df_season[df_season['学年'].isin(target_grades)].copy()
    
    # 識別用カラムを削除してテーブル表示
    drop_cols = ['ID']
    display_df = filtered_df.drop(columns=[c for c in drop_cols if c in filtered_df.columns], errors='ignore').set_index('氏名')
    
    st.subheader(f"{target_season} データ一覧 (各カラムをクリックしてソート可能)")
    st.dataframe(display_df)
    
    st.markdown("---")
    st.subheader("📊 ランキング・偏差 散布図")
    test_items = [c for c in filtered_df.columns if c not in ['ID', '氏名', '学年']]
    selected_test = st.selectbox("比較するテストを選択", test_items)
    
    if selected_test:
        plot_df = filtered_df[['氏名', '学年', selected_test]].copy()
        plot_df[selected_test] = pd.to_numeric(plot_df[selected_test], errors='coerce')
        plot_df = plot_df.dropna(subset=[selected_test])
        
        # 10m走や505テスト（タイム）の場合は小さい方が上位（昇順）
        # それ以外（距離、回数、スピード等）は大きい方が上位（降順）
        is_time_metric = ("走" in selected_test or "505" in selected_test)
        
        plot_df = plot_df.sort_values(by=selected_test, ascending=is_time_metric).reset_index(drop=True)
        plot_df['順位'] = plot_df.index + 1
        
        if not plot_df.empty:
            avg_val = plot_df[selected_test].mean()
            
            # メトリクス表示
            st.markdown(f"**【{selected_test}】 トップ＆平均データ**")
            top_val = plot_df.iloc[0][selected_test]
            top_name = plot_df.iloc[0]['氏名']
            
            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("全体平均", f"{avg_val:.2f}")
            col_m2.metric("トップ記録", f"{top_val:.2f}", f"{top_name} 選手")
            col_m3.metric("データ件数", f"{len(plot_df)}名")

            import plotly.express as px
            import plotly.graph_objects as go
            
            # カテゴリカルX軸を成績順で固定するためにcategory_ordersを指定
            fig_scatter = px.scatter(
                plot_df, x="氏名", y=selected_test, color="学年",
                hover_data={"氏名": True, "学年": True, selected_test: True, "順位": True},
                title=f"{selected_test} のランキング分布 ({target_season})",
                category_orders={"氏名": plot_df["氏名"].tolist()},
                template=theme_template
            )
            fig_scatter.update_traces(marker=dict(size=14, line=dict(width=1, color='DarkSlateGrey')))
            
            # 平均線の追加
            fig_scatter.add_hline(
                y=avg_val, line_dash="dash", line_color="tomato",
                annotation_text=f"平均: {avg_val:.2f}", annotation_position="top right"
            )
            
            st.plotly_chart(fig_scatter, use_container_width=True)
            
            # テーブルでの詳細な順位表示
            with st.expander("📋 詳細ランキング表を見る"):
                table_df = plot_df[['順位', '氏名', '学年', selected_test]].copy()
                table_df['平均との差'] = table_df[selected_test] - avg_val
                table_df['平均との差'] = table_df['平均との差'].apply(lambda x: f"{x:+.2f}")
                st.dataframe(table_df.set_index('順位'), use_container_width=True)
            
        else:
            st.write(f"※ {target_season} における {selected_test} の有効なデータがありません。")

    st.markdown("---")
    st.subheader("🏃 アジリティ分析 (4象限マップ: 10m走 vs 505テスト)")
    st.markdown("10m走(スプリント能力)と505テスト(方向転換能力)の相関と、全体平均を基準にした強み・弱みを分析します。")

    if '10m走' in filtered_df.columns and '505テスト' in filtered_df.columns:
        ag_df = filtered_df[['氏名', '学年', '10m走', '505テスト']].copy()
        ag_df['10m走'] = pd.to_numeric(ag_df['10m走'], errors='coerce')
        ag_df['505テスト'] = pd.to_numeric(ag_df['505テスト'], errors='coerce')
        ag_df = ag_df.dropna(subset=['10m走', '505テスト'])

        if not ag_df.empty:
            avg_10m = ag_df['10m走'].mean()
            avg_505 = ag_df['505テスト'].mean()
            
            # 名字抽出ロジック
            def get_last_name(name):
                if pd.isna(name): return ""
                name = str(name).strip()
                if ' ' in name or '　' in name:
                    return name.replace('　', ' ').split(' ')[0]
                
                # 既知の部員リスト（スペース無しのフルネームから名字を正確に切り出す）
                known = {
                    '五十嵐美結': '五十嵐', '尾崎瀬里奈': '尾崎', '樫尾陽和里': '樫尾', '左近知美': '左近',
                    '生井沢日向子': '生井沢', '細田美帆': '細田', '入澤瑛麻': '入澤', '髙橋ひかる': '髙橋',
                    '天間美嘉': '天間', '橋本和香菜': '橋本', '藤井真菜': '藤井', '松岡琴美': '松岡',
                    '吉木理彩': '吉木', '渡邉妃菜乃': '渡邉', '加藤華': '加藤', '長根理子': '長根',
                    '岩田愛美': '岩田', '内田真愛': '内田', '中村楓芽': '中村', '向山せら': '向山',
                    '山下永遠': '山下', '徳山暖枝': '徳山', '池田朝花': '池田', '濱口芽花': '濱口',
                    '濱田遥花': '濱田', '林美桜': '林', '津島世奈': '津島', '後藤和香奈': '後藤'
                }
                if name in known:
                    return known[name]
                # 新規選手（辞書にない）場合のおおよその判定
                return name[:2] if len(name) >= 3 else name
                
            ag_df['名字'] = ag_df['氏名'].apply(get_last_name)
            name_counts = ag_df['名字'].value_counts()
            
            def resolve_name(row):
                lname = row['名字']
                # 天間選手については名前被り判定をせず「天間」にする例外処理
                if lname == '天間':
                    return '天間'
                    
                # 同じ名字がグラフ上に複数いる場合は「下の名前の頭文字」を付ける
                if name_counts.get(lname, 0) > 1:
                    fname = row['氏名'].replace(lname, '')
                    if fname:
                        return f"{lname}({fname[0]})"
                return lname
                
            ag_df['表示名'] = ag_df.apply(resolve_name, axis=1)
            
            # タイムのため逆順(reversed)にプロットすることで、左下を「最速(優秀)」にする
            fig_ag = px.scatter(
                ag_df, x='10m走', y='505テスト', color='学年', hover_name='氏名',
                text='表示名',
                title=f"アジリティ相関 ({target_season})",
                template=theme_template
            )
            # マーカーの調整とテキスト位置
            fig_ag.update_traces(
                textposition='bottom center',
                marker=dict(size=14, line=dict(width=1, color='DarkSlateGrey'))
            )
            
            # X軸、Y軸を反転させる
            fig_ag.update_xaxes(autorange="reversed")
            fig_ag.update_yaxes(autorange="reversed")

            # 平均線の追加（これで4象限に分割）
            fig_ag.add_hline(y=avg_505, line_dash="dash", line_color="tomato", annotation_text="505平均")
            fig_ag.add_vline(x=avg_10m, line_dash="dash", line_color="tomato", annotation_text="10m平均")

            st.plotly_chart(fig_ag, use_container_width=True)
            st.info("💡 **見方**: 左下にいくほど両方のタイムが速く（優秀）、右上にいくほど遅いことを示します。")

elif view_mode == "チーム全体の推移 (時系列)":
    st.header("📈 チーム全体の推移 (全体平均・コホート別平均)")
    st.markdown("記録の平均値が時期ごとにどう変化しているかを折れ線グラフで確認できます。学年は**「現在の学年」**基準で追跡（コホート分析）されます。")
    
    analysis_scope = st.radio("🎯 集計対象の絞り込み", ["全体 (全学年・OG含む)", "🔰 体づくりサポート対象のみ (現在の2, 3, 4年生)"], index=0, horizontal=True)
    st.markdown("---")
    
    if not fitness_data_dict:
        st.warning("データがありません。")
        st.stop()
    # 全データを縦持ち(long format)に変換する
    all_data = []
    for season, df in fitness_data_dict.items():
        temp = df.copy()
        temp['測定時期'] = season
        
        # コホート分析のため、25年度(25年冬)の学年を26年度(現在)に合わせる
        def adjust_grade(g):
            if pd.isna(g):
                return 'OG/その他'
            g_str = str(g).replace("年", "").replace("(現在)", "").strip()
            if g_str.isdigit():
                num = int(g_str)
                # 25年冬の場合は学年を+1する（当時の4年生は卒業）
                if season == "25年冬":
                    if num == 4:
                        return 'OG/その他'
                    return f"{num + 1}年(現在)"
                else:
                    return f"{num}年(現在)"
            return str(g)
            
        temp['学年'] = temp['学年'].apply(adjust_grade)
        all_data.append(temp)
    
    combined_df = pd.concat(all_data, ignore_index=True)
    
    # 対象者の絞り込み
    if "サポート対象" in analysis_scope:
        valid_grades = ["2年(現在)", "3年(現在)", "4年(現在)"]
        combined_df = combined_df[combined_df['学年'].isin(valid_grades)]
    
    # 比較可能なテスト項目を取得
    test_items = [c for c in combined_df.columns if c not in ['ID', '氏名', '学年', '測定時期']]
    
    selected_test = st.selectbox("確認したいテスト項目を選択", test_items)
    
    if selected_test:
        import plotly.express as px
        
        # 数値データに変換
        combined_df[selected_test] = pd.to_numeric(combined_df[selected_test], errors='coerce')
        
        # 全体平均を算出
        avg_df_overall = combined_df.groupby('測定時期')[selected_test].mean().reset_index()
        avg_df_overall['学年'] = '🔥 全体平均'
        
        # 学年別平均を算出
        avg_df_grade = combined_df.groupby(['測定時期', '学年'])[selected_test].mean().reset_index()
        
        plot_avg_df = pd.concat([avg_df_overall, avg_df_grade], ignore_index=True)
        # 測定時期の順序を保持
        seasons_order = list(fitness_data_dict.keys())
        plot_avg_df['測定時期'] = pd.Categorical(plot_avg_df['測定時期'], categories=seasons_order, ordered=True)
        plot_avg_df = plot_avg_df.sort_values('測定時期')
        plot_avg_df = plot_avg_df.dropna(subset=[selected_test])
        
        if not plot_avg_df.empty:
            
            # Y軸の自動反転（タイム系）
            is_time_metric = ("走" in selected_test or "505" in selected_test)
            
            fig_trend = px.line(
                plot_avg_df, x='測定時期', y=selected_test, color='学年',
                markers=True, text=plot_avg_df[selected_test].apply(lambda x: f"{x:.2f}"),
                title=f"{selected_test} の推移",
                category_orders={"測定時期": seasons_order},
                template=theme_template
            )
            # 全体平均の線を強調する
            for trace in fig_trend.data:
                if trace.name == "🔥 全体平均":
                    trace.line.width = 4
                    trace.line.color = "#FF4B4B"
                    trace.marker.size = 10
                else:
                    trace.line.width = 2
                    trace.line.dash = 'dot'
            
            fig_trend.update_traces(textposition="top center")
            if is_time_metric:
                fig_trend.update_yaxes(autorange="reversed")
                st.info("※ タイム系のため、上に行くほどグラフが高い位置（小さな数値・速いタイム）になるよう反転しています。")
                
            st.plotly_chart(fig_trend, use_container_width=True)
            
            # データーテーブル
            with st.expander("📋 平均値の詳細データを見る"):
                try:
                    pivot_df = plot_avg_df.pivot(index='測定時期', columns='学年', values=selected_test).round(2)
                    # 全体平均を一番左に持ってくる
                    cols = pivot_df.columns.tolist()
                    if '🔥 全体平均' in cols:
                        cols.insert(0, cols.pop(cols.index('🔥 全体平均')))
                        pivot_df = pivot_df[cols]
                    st.dataframe(pivot_df, use_container_width=True)
                except Exception as e:
                    st.write("テーブル表示エラー (重複データなどが原因の可能性があります)")
                    
            # ----------------------------------------------------
            # 個別データ推移 (全員分グラフ + ソート機能付きテーブル)
            # ----------------------------------------------------
            st.markdown("---")
            st.subheader("👤 全員の個別データ推移")
            st.markdown("選手ごとの記録の推移と、成長度（初回と最新の差分）を確認できます。下の表は見たい項目（最新時期など）をクリックしてソート可能です。")
            
            indiv_df = combined_df[['測定時期', '学年', '氏名', selected_test]].copy()
            indiv_df = indiv_df.dropna(subset=[selected_test])
            
            if not indiv_df.empty:
                # グラフ描画
                fig_indiv = px.line(
                    indiv_df, x='測定時期', y=selected_test, color='氏名', line_group='氏名',
                    hover_name='氏名', hover_data={'学年': True},
                    markers=True,
                    title=f"{selected_test} の推移 (個人別)",
                    category_orders={"測定時期": seasons_order},
                    template=theme_template
                )
                fig_indiv.update_traces(line=dict(width=1.5), marker=dict(size=6), opacity=0.8)
                
                if is_time_metric:
                    fig_indiv.update_yaxes(autorange="reversed")
                
                st.plotly_chart(fig_indiv, use_container_width=True)
                
                # Pivot機能で全員の成績をテーブル化 (重複データがある場合は平均をとってエラー回避)
                indiv_pivot = indiv_df.pivot_table(index=['氏名', '学年'], columns='測定時期', values=selected_test, aggfunc='mean').reset_index()
                
                # デフォルトは最新時期の成績順にソートする
                recent_seasons = [s for s in reversed(seasons_order) if s in indiv_pivot.columns]
                if recent_seasons:
                    sort_target = recent_seasons[0]
                    indiv_pivot = indiv_pivot.sort_values(by=sort_target, ascending=is_time_metric)
                
                # 差分（成長度）を計算
                available_seasons = [s for s in seasons_order if s in indiv_pivot.columns]
                if len(available_seasons) >= 2:
                    first_s = available_seasons[0]
                    latest_s = available_seasons[-1]
                    indiv_pivot['記録の差 (最新 - 初回)'] = indiv_pivot[latest_s] - indiv_pivot[first_s]
                    
                    if is_time_metric: # タイムはマイナスが良い
                        indiv_pivot['評価'] = indiv_pivot['記録の差 (最新 - 初回)'].apply(lambda x: '🔵 向上' if pd.notna(x) and x < 0 else ('--' if pd.isna(x) or x==0 else '🔻'))
                    else:              # 回数・スピードはプラスが良い
                        indiv_pivot['評価'] = indiv_pivot['記録の差 (最新 - 初回)'].apply(lambda x: '🔴 向上' if pd.notna(x) and x > 0 else ('--' if pd.isna(x) or x==0 else '🔻'))
                
                st.markdown("##### 📋 個別データの詳細テーブル (項目クリックでソート)")
                st.dataframe(indiv_pivot.set_index('氏名'), use_container_width=True)

        else:
            st.info("プロット可能なデータがありません。")
