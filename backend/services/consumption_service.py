"""
消费数据分析服务
从景区游客消费数据中分析各项指标
"""

import os
import csv
import json
from datetime import datetime
from collections import Counter, defaultdict
from typing import List, Dict, Any, Optional


# 灵山景区关键词，用于从全量数据中筛选
LINSAN_KEYWORDS = ['灵山', '拈花湾', '无锡', '太湖鼋头渚', '三国水浒', '惠山古镇']

# 默认数据文件路径（后端 consumption_data 目录）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONSUMPTION_DATA_DIR = os.path.join(BASE_DIR, 'backend', 'consumption_data')
DEFAULT_CSV = os.path.join(CONSUMPTION_DATA_DIR, 'lingsan_consumption_data.csv')
DEFAULT_JSON = os.path.join(CONSUMPTION_DATA_DIR, 'lingsan_consumption_data.json')


def load_csv_data(filepath: str) -> List[Dict[str, Any]]:
    """加载CSV消费数据"""
    records = []
    if not os.path.exists(filepath):
        return records
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    record = {
                        'tourist_id': row.get('tourist_id', ''),
                        'user_nickname': row.get('user_nickname', ''),
                        'age': int(row.get('age', 0)) if row.get('age', '0').isdigit() else 0,
                        'gender': row.get('gender', ''),
                        'attraction_name': row.get('attraction_name', ''),
                        'attraction_type': row.get('attraction_type', ''),
                        'visit_date': row.get('visit_date', ''),
                        'stay_duration': float(row.get('stay_duration', 0)) if row.get('stay_duration') else 0,
                        'ticket_cost': float(row.get('ticket_cost', 0)) if row.get('ticket_cost') else 0,
                        'food_cost': float(row.get('food_cost', 0)) if row.get('food_cost') else 0,
                        'shopping_cost': float(row.get('shopping_cost', 0)) if row.get('shopping_cost') else 0,
                        'transport_cost': float(row.get('transport_cost', 0)) if row.get('transport_cost') else 0,
                        'entertainment_cost': float(row.get('entertainment_cost', 0)) if row.get('entertainment_cost') else 0,
                        'total_cost': float(row.get('total_cost', 0)) if row.get('total_cost') else 0,
                        'group_size': int(row.get('group_size', 0)) if row.get('group_size', '0').isdigit() else 0,
                        'satisfaction': int(row.get('satisfaction', 0)) if row.get('satisfaction', '0').isdigit() else 0,
                    }
                    records.append(record)
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        print(f"[Consumption] 读取CSV失败: {e}")
    
    return records


def load_json_data(filepath: str) -> List[Dict[str, Any]]:
    """加载JSON消费数据"""
    records = []
    if not os.path.exists(filepath):
        return records
    
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            raw = json.load(f)
            for item in raw:
                record = {
                    'tourist_id': item.get('user_id', ''),
                    'user_nickname': item.get('name', ''),
                    'age': int(item.get('age', 0)),
                    'gender': item.get('gender', ''),
                    'attraction_name': item.get('scenic_spot', ''),
                    'attraction_type': item.get('spot_type', ''),
                    'visit_date': item.get('visit_date', ''),
                    'stay_duration': float(item.get('stay_duration', 0)),
                    'ticket_cost': float(item.get('ticket_cost', 0)),
                    'food_cost': float(item.get('food_cost', 0)),
                    'shopping_cost': float(item.get('shopping_cost', 0)),
                    'transport_cost': float(item.get('transport_cost', 0)),
                    'entertainment_cost': float(item.get('entertainment_cost', 0)),
                    'total_cost': float(item.get('total_cost', 0)),
                    'group_size': int(item.get('group_size', 0)),
                    'satisfaction': int(item.get('satisfaction', 0)),
                }
                records.append(record)
    except Exception as e:
        print(f"[Consumption] 读取JSON失败: {e}")
    
    return records


def load_consumption_data() -> List[Dict[str, Any]]:
    """优先从CSV加载，若不存在则尝试JSON"""
    records = load_csv_data(DEFAULT_CSV)
    if not records:
        records = load_json_data(DEFAULT_JSON)
    return records


def _avg(values: List[float]) -> float:
    """安全求均值"""
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _sum(values: List[float]) -> float:
    """安全求和"""
    return round(sum(values), 2)


def _get_age_group(age: int) -> str:
    """年龄分组"""
    if age < 18:
        return '18岁以下'
    elif age < 25:
        return '18-25岁'
    elif age < 35:
        return '25-35岁'
    elif age < 45:
        return '35-45岁'
    elif age < 55:
        return '45-55岁'
    elif age < 65:
        return '55-65岁'
    else:
        return '65岁以上'


def _get_month_label(date_str: str) -> Optional[str]:
    """从日期字符串提取月份标签"""
    if not date_str:
        return None
    try:
        # 支持格式: '2025-08-13 00:00:00' or '2025-08-13T00:00:00'
        cleaned = date_str.replace('T', ' ').split(' ')[0]
        dt = datetime.strptime(cleaned, '%Y-%m-%d')
        return dt.strftime('%Y-%m')
    except (ValueError, TypeError):
        return None


def _get_satisfaction_label(score: int) -> str:
    """满意度标签"""
    if score >= 5:
        return '非常满意'
    elif score >= 4:
        return '满意'
    elif score >= 3:
        return '一般'
    elif score >= 2:
        return '不满意'
    else:
        return '非常不满意'


def _get_satisfaction_level(score: int) -> str:
    """满意度等级（用于分析建议）"""
    if score >= 4:
        return '高'
    elif score >= 3:
        return '中'
    else:
        return '低'


# ===================== 1. 消费总览 =====================
def get_consumption_overview(records: List[Dict] = None) -> Dict[str, Any]:
    """获取消费数据总览统计"""
    if records is None:
        records = load_consumption_data()
    
    total = len(records)
    if total == 0:
        return {'code': 200, 'data': _empty_overview()}
    
    all_total_cost = [r['total_cost'] for r in records]
    all_ticket = [r['ticket_cost'] for r in records]
    all_food = [r['food_cost'] for r in records]
    all_shopping = [r['shopping_cost'] for r in records]
    all_transport = [r['transport_cost'] for r in records]
    all_entertainment = [r['entertainment_cost'] for r in records]
    all_satisfaction = [r['satisfaction'] for r in records]
    all_group_size = [r['group_size'] for r in records]
    all_stay = [r['stay_duration'] for r in records]
    
    total_revenue = _sum(all_total_cost)
    avg_total = _avg(all_total_cost)
    avg_ticket = _avg(all_ticket)
    avg_food = _avg(all_food)
    avg_shopping = _avg(all_shopping)
    avg_transport = _avg(all_transport)
    avg_entertainment = _avg(all_entertainment)
    avg_satisfaction = _avg(all_satisfaction)
    avg_group = _avg(all_group_size)
    avg_stay = _avg(all_stay)
    
    # 消费结构占比
    total_ticket = _sum(all_ticket)
    total_food = _sum(all_food)
    total_shopping = _sum(all_shopping)
    total_transport = _sum(all_transport)
    total_entertainment = _sum(all_entertainment)
    cost_sum = total_ticket + total_food + total_shopping + total_transport + total_entertainment
    
    structure = {
        'ticket': {'amount': total_ticket, 'ratio': round(total_ticket / cost_sum * 100, 1) if cost_sum > 0 else 0},
        'food': {'amount': total_food, 'ratio': round(total_food / cost_sum * 100, 1) if cost_sum > 0 else 0},
        'shopping': {'amount': total_shopping, 'ratio': round(total_shopping / cost_sum * 100, 1) if cost_sum > 0 else 0},
        'transport': {'amount': total_transport, 'ratio': round(total_transport / cost_sum * 100, 1) if cost_sum > 0 else 0},
        'entertainment': {'amount': total_entertainment, 'ratio': round(total_entertainment / cost_sum * 100, 1) if cost_sum > 0 else 0},
    }
    
    # 满意度分布
    sat_counter = Counter(r['satisfaction'] for r in records if r['satisfaction'])
    sat_distribution = {str(k): v for k, v in sorted(sat_counter.items())}
    high_sat_count = sum(1 for s in all_satisfaction if s >= 4)
    high_sat_ratio = round(high_sat_count / total * 100, 1) if total > 0 else 0
    
    # 景区名称统计
    spot_counter = Counter(r['attraction_name'] for r in records if r['attraction_name'])
    top_spots = [{'name': k, 'count': v} for k, v in spot_counter.most_common(5)]
    
    return {
        'code': 200,
        'data': {
            'total_visitors': total,
            'total_revenue': total_revenue,
            'avg_total_cost': avg_total,
            'avg_ticket_cost': avg_ticket,
            'avg_food_cost': avg_food,
            'avg_shopping_cost': avg_shopping,
            'avg_transport_cost': avg_transport,
            'avg_entertainment_cost': avg_entertainment,
            'cost_structure': structure,
            'avg_satisfaction': avg_satisfaction,
            'satisfaction_distribution': sat_distribution,
            'high_satisfaction_ratio': high_sat_ratio,
            'avg_group_size': avg_group,
            'avg_stay_duration': avg_stay,
            'top_attractions': top_spots,
        }
    }


def _empty_overview():
    return {
        'total_visitors': 0, 'total_revenue': 0, 'avg_total_cost': 0,
        'avg_ticket_cost': 0, 'avg_food_cost': 0, 'avg_shopping_cost': 0,
        'avg_transport_cost': 0, 'avg_entertainment_cost': 0,
        'cost_structure': {}, 'avg_satisfaction': 0,
        'satisfaction_distribution': {}, 'high_satisfaction_ratio': 0,
        'avg_group_size': 0, 'avg_stay_duration': 0, 'top_attractions': []
    }


# ===================== 2. 月度消费趋势 =====================
def get_monthly_trend(records: List[Dict] = None) -> Dict[str, Any]:
    """按月度统计消费趋势"""
    if records is None:
        records = load_consumption_data()
    
    monthly_data = defaultdict(lambda: {
        'visitors': 0, 'total_cost_sum': 0.0, 'ticket_sum': 0.0,
        'food_sum': 0.0, 'shopping_sum': 0.0, 'transport_sum': 0.0,
        'entertainment_sum': 0.0, 'satisfaction_sum': 0.0
    })
    
    for r in records:
        month = _get_month_label(r['visit_date'])
        if not month:
            continue
        d = monthly_data[month]
        d['visitors'] += 1
        d['total_cost_sum'] += r['total_cost']
        d['ticket_sum'] += r['ticket_cost']
        d['food_sum'] += r['food_cost']
        d['shopping_sum'] += r['shopping_cost']
        d['transport_sum'] += r['transport_cost']
        d['entertainment_sum'] += r['entertainment_cost']
        d['satisfaction_sum'] += r['satisfaction']
    
    result = []
    for month in sorted(monthly_data.keys()):
        d = monthly_data[month]
        visitors = d['visitors']
        result.append({
            'month': month,
            'visitors': visitors,
            'avg_total_cost': round(d['total_cost_sum'] / visitors, 2) if visitors > 0 else 0,
            'total_revenue': round(d['total_cost_sum'], 2),
            'avg_ticket': round(d['ticket_sum'] / visitors, 2) if visitors > 0 else 0,
            'avg_food': round(d['food_sum'] / visitors, 2) if visitors > 0 else 0,
            'avg_shopping': round(d['shopping_sum'] / visitors, 2) if visitors > 0 else 0,
            'avg_transport': round(d['transport_sum'] / visitors, 2) if visitors > 0 else 0,
            'avg_entertainment': round(d['entertainment_sum'] / visitors, 2) if visitors > 0 else 0,
            'avg_satisfaction': round(d['satisfaction_sum'] / visitors, 2) if visitors > 0 else 0,
        })
    
    return {'code': 200, 'data': result}


# ===================== 3. 年龄段消费分析 =====================
def get_age_analysis(records: List[Dict] = None) -> Dict[str, Any]:
    """按年龄段分析消费"""
    if records is None:
        records = load_consumption_data()
    
    age_groups = defaultdict(lambda: {
        'count': 0, 'total_sum': 0.0, 'ticket_sum': 0.0,
        'food_sum': 0.0, 'shopping_sum': 0.0, 'transport_sum': 0.0,
        'entertainment_sum': 0.0, 'sat_sum': 0.0, 'stay_sum': 0.0
    })
    
    for r in records:
        group = _get_age_group(r['age'])
        d = age_groups[group]
        d['count'] += 1
        d['total_sum'] += r['total_cost']
        d['ticket_sum'] += r['ticket_cost']
        d['food_sum'] += r['food_cost']
        d['shopping_sum'] += r['shopping_cost']
        d['transport_sum'] += r['transport_cost']
        d['entertainment_sum'] += r['entertainment_cost']
        d['sat_sum'] += r['satisfaction']
        d['stay_sum'] += r['stay_duration']
    
    # 排序
    order = ['18岁以下', '18-25岁', '25-35岁', '35-45岁', '45-55岁', '55-65岁', '65岁以上']
    result = []
    for group in order:
        if group not in age_groups:
            continue
        d = age_groups[group]
        n = d['count']
        result.append({
            'age_group': group,
            'count': n,
            'ratio': round(n / len(records) * 100, 1) if records else 0,
            'avg_total': round(d['total_sum'] / n, 2) if n > 0 else 0,
            'avg_ticket': round(d['ticket_sum'] / n, 2) if n > 0 else 0,
            'avg_food': round(d['food_sum'] / n, 2) if n > 0 else 0,
            'avg_shopping': round(d['shopping_sum'] / n, 2) if n > 0 else 0,
            'avg_transport': round(d['transport_sum'] / n, 2) if n > 0 else 0,
            'avg_entertainment': round(d['entertainment_sum'] / n, 2) if n > 0 else 0,
            'avg_satisfaction': round(d['sat_sum'] / n, 2) if n > 0 else 0,
            'avg_stay': round(d['stay_sum'] / n, 2) if n > 0 else 0,
        })
    
    return {'code': 200, 'data': result}


# ===================== 4. 消费 vs 满意度交叉分析 =====================
def get_satisfaction_cost_analysis(records: List[Dict] = None) -> Dict[str, Any]:
    """消费区间 × 满意度交叉分析"""
    if records is None:
        records = load_consumption_data()
    
    # 定义消费区间
    def cost_bracket(total):
        if total < 300:
            return '低消费(<300)'
        elif total < 600:
            return '中低消费(300-600)'
        elif total < 1000:
            return '中消费(600-1000)'
        elif total < 1500:
            return '中高消费(1000-1500)'
        else:
            return '高消费(≥1500)'
    
    brackets = defaultdict(lambda: defaultdict(int))
    bracket_sums = defaultdict(lambda: defaultdict(float))
    
    for r in records:
        b = cost_bracket(r['total_cost'])
        s = r['satisfaction']
        brackets[b][s] += 1
        bracket_sums[b]['total'] += r['total_cost']
        bracket_sums[b]['satisfaction'] += s
        bracket_sums[b]['count'] += 1
    
    result = []
    bracket_order = ['低消费(<300)', '中低消费(300-600)', '中消费(600-1000)', '中高消费(1000-1500)', '高消费(≥1500)']
    for b in bracket_order:
        if b not in brackets:
            continue
        sat_dist = brackets[b]
        n = bracket_sums[b]['count']
        high_sat = sat_dist.get(4, 0) + sat_dist.get(5, 0)
        low_sat = sat_dist.get(1, 0) + sat_dist.get(2, 0)
        result.append({
            'bracket': b,
            'total_count': n,
            'satisfaction_dist': {str(k): v for k, v in sorted(sat_dist.items())},
            'avg_total_cost': round(bracket_sums[b]['total'] / n, 2) if n > 0 else 0,
            'avg_satisfaction': round(bracket_sums[b]['satisfaction'] / n, 2) if n > 0 else 0,
            'high_satisfaction_ratio': round(high_sat / n * 100, 1) if n > 0 else 0,
            'low_satisfaction_ratio': round(low_sat / n * 100, 1) if n > 0 else 0,
        })
    
    # 计算"高消费低满意"人数
    high_cost_low_sat = sum(1 for r in records if r['total_cost'] >= 1000 and r['satisfaction'] <= 3)
    high_cost_total = sum(1 for r in records if r['total_cost'] >= 1000)
    
    return {
        'code': 200,
        'data': {
            'cross_analysis': result,
            'high_cost_low_sat_count': high_cost_low_sat,
            'high_cost_total_count': high_cost_total,
            'high_cost_low_sat_ratio': round(high_cost_low_sat / high_cost_total * 100, 1) if high_cost_total > 0 else 0,
        }
    }


# ===================== 5. 性别消费对比 =====================
def get_gender_analysis(records: List[Dict] = None) -> Dict[str, Any]:
    """按性别对比消费"""
    if records is None:
        records = load_consumption_data()
    
    gender_data = defaultdict(lambda: {
        'count': 0, 'total_sum': 0.0, 'ticket_sum': 0.0,
        'food_sum': 0.0, 'shopping_sum': 0.0, 'transport_sum': 0.0,
        'entertainment_sum': 0.0, 'sat_sum': 0.0
    })
    
    for r in records:
        g = r['gender'] or '未知'
        d = gender_data[g]
        d['count'] += 1
        d['total_sum'] += r['total_cost']
        d['ticket_sum'] += r['ticket_cost']
        d['food_sum'] += r['food_cost']
        d['shopping_sum'] += r['shopping_cost']
        d['transport_sum'] += r['transport_cost']
        d['entertainment_sum'] += r['entertainment_cost']
        d['sat_sum'] += r['satisfaction']
    
    result = []
    for g, d in gender_data.items():
        n = d['count']
        result.append({
            'gender': g,
            'count': n,
            'ratio': round(n / len(records) * 100, 1) if records else 0,
            'avg_total': round(d['total_sum'] / n, 2) if n > 0 else 0,
            'avg_ticket': round(d['ticket_sum'] / n, 2) if n > 0 else 0,
            'avg_food': round(d['food_sum'] / n, 2) if n > 0 else 0,
            'avg_shopping': round(d['shopping_sum'] / n, 2) if n > 0 else 0,
            'avg_transport': round(d['transport_sum'] / n, 2) if n > 0 else 0,
            'avg_entertainment': round(d['entertainment_sum'] / n, 2) if n > 0 else 0,
            'avg_satisfaction': round(d['sat_sum'] / n, 2) if n > 0 else 0,
        })
    
    return {'code': 200, 'data': result}


# ===================== 6. 停留时长与消费关系 =====================
def get_stay_cost_analysis(records: List[Dict] = None) -> Dict[str, Any]:
    """停留时长与消费关系分析"""
    if records is None:
        records = load_consumption_data()
    
    # 停留时长分组
    def stay_group(hours):
        if hours < 3:
            return '短时间(<3h)'
        elif hours < 6:
            return '中短(3-6h)'
        elif hours < 10:
            return '中(6-10h)'
        else:
            return '长时间(≥10h)'
    
    stay_data = defaultdict(lambda: {'count': 0, 'total_sum': 0.0, 'sat_sum': 0.0})
    
    for r in records:
        g = stay_group(r['stay_duration'])
        d = stay_data[g]
        d['count'] += 1
        d['total_sum'] += r['total_cost']
        d['sat_sum'] += r['satisfaction']
    
    order = ['短时间(<3h)', '中短(3-6h)', '中(6-10h)', '长时间(≥10h)']
    result = []
    for g in order:
        if g not in stay_data:
            continue
        d = stay_data[g]
        n = d['count']
        result.append({
            'stay_group': g,
            'count': n,
            'avg_total_cost': round(d['total_sum'] / n, 2) if n > 0 else 0,
            'avg_satisfaction': round(d['sat_sum'] / n, 2) if n > 0 else 0,
        })
    
    return {'code': 200, 'data': result}


# ===================== 7. 景区类型消费对比 =====================
def get_type_analysis(records: List[Dict] = None) -> Dict[str, Any]:
    """按景区类型分析消费"""
    if records is None:
        records = load_consumption_data()
    
    type_data = defaultdict(lambda: {'count': 0, 'total_sum': 0.0, 'ticket_sum': 0.0, 'food_sum': 0.0, 'shopping_sum': 0.0, 'transport_sum': 0.0, 'entertainment_sum': 0.0, 'sat_sum': 0.0})
    
    for r in records:
        t = r['attraction_type'] or '未知'
        d = type_data[t]
        d['count'] += 1
        d['total_sum'] += r['total_cost']
        d['ticket_sum'] += r['ticket_cost']
        d['food_sum'] += r['food_cost']
        d['shopping_sum'] += r['shopping_cost']
        d['transport_sum'] += r['transport_cost']
        d['entertainment_sum'] += r['entertainment_cost']
        d['sat_sum'] += r['satisfaction']
    
    result = []
    for t, d in type_data.items():
        n = d['count']
        result.append({
            'spot_type': t,
            'count': n,
            'avg_total': round(d['total_sum'] / n, 2) if n > 0 else 0,
            'avg_ticket': round(d['ticket_sum'] / n, 2) if n > 0 else 0,
            'avg_food': round(d['food_sum'] / n, 2) if n > 0 else 0,
            'avg_shopping': round(d['shopping_sum'] / n, 2) if n > 0 else 0,
            'avg_transport': round(d['transport_sum'] / n, 2) if n > 0 else 0,
            'avg_entertainment': round(d['entertainment_sum'] / n, 2) if n > 0 else 0,
            'avg_satisfaction': round(d['sat_sum'] / n, 2) if n > 0 else 0,
        })
    
    result.sort(key=lambda x: x['avg_total'], reverse=True)
    return {'code': 200, 'data': result}


# ===================== 8. 生成运营建议 =====================
def get_operational_insights(records: List[Dict] = None) -> Dict[str, Any]:
    """基于数据生成运营分析建议"""
    if records is None:
        records = load_consumption_data()
    
    if not records:
        return {'code': 200, 'data': {'insights': [], 'recommendations': []}}
    
    total = len(records)
    all_total_cost = [r['total_cost'] for r in records]
    all_satisfaction = [r['satisfaction'] for r in records]
    all_food = [r['food_cost'] for r in records]
    all_shopping = [r['shopping_cost'] for r in records]
    all_ticket = [r['ticket_cost'] for r in records]
    
    avg_total = _avg(all_total_cost)
    avg_satisfaction = _avg(all_satisfaction)
    avg_food = _avg(all_food)
    avg_shopping = _avg(all_shopping)
    avg_ticket = _avg(all_ticket)
    
    # 消费结构占比
    total_cost_sum = sum(all_total_cost)
    total_food_sum = sum(all_food)
    total_shopping_sum = sum(all_shopping)
    total_ticket_sum = sum(all_ticket)
    
    food_ratio = total_food_sum / total_cost_sum * 100 if total_cost_sum > 0 else 0
    shopping_ratio = total_shopping_sum / total_cost_sum * 100 if total_cost_sum > 0 else 0
    
    # 高消费低满意人数
    high_cost_low_sat = sum(1 for r in records if r['total_cost'] >= 1000 and r['satisfaction'] <= 3)
    
    # 满意度分布
    high_sat = sum(1 for s in all_satisfaction if s >= 4)
    high_sat_ratio = high_sat / total * 100 if total > 0 else 0
    
    insights = []
    recommendations = []
    
    # 洞察1：整体消费水平
    insights.append({
        'category': '整体消费',
        'text': f'灵山大佛景区共接待 {total} 名游客，人均总消费 ¥{avg_total:.2f}，总消费额 ¥{total_cost_sum:.2f}。'
    })
    
    # 洞察2：消费结构
    insights.append({
        'category': '消费结构',
        'text': f'消费结构中餐饮占比 {food_ratio:.1f}%，购物占比 {shopping_ratio:.1f}%，两项合计占二次消费主体。门票占比 {total_ticket_sum/total_cost_sum*100:.1f}%，说明景区二次消费是主要收入来源。'
    })
    
    # 洞察3：满意度
    insights.append({
        'category': '游客满意度',
        'text': f'平均满意度 {avg_satisfaction:.2f}/5，高满意（4-5分）游客占比 {high_sat_ratio:.1f}%。'
    })
    
    # 洞察4：高消费低满意
    if high_cost_low_sat > 0:
        insights.append({
            'category': '消费与满意度矛盾',
            'text': f'发现 {high_cost_low_sat} 名游客消费超过 ¥1000 但满意度≤3分，存在"高消费低满意"现象，需重点关注。'
        })
        recommendations.append({
            'priority': '高',
            'title': '优化高消费游客体验',
            'detail': f'针对消费超¥1000但满意度低的{high_cost_low_sat}名游客，建议：①提升梵宫演出《灵山吉祥颂》质量；②优化景区餐饮品质与定价；③增加专属VIP服务通道。'
        })
    
    # 洞察5：餐饮购物
    if food_ratio > 25:
        recommendations.append({
            'priority': '高',
            'title': '餐饮体验优化',
            'detail': f'餐饮消费占比高达{food_ratio:.1f}%，建议：①引入高端素食品牌提升档次；②推出灵山特色禅意套餐；③优化景区内餐饮分布密度。'
        })
    
    if shopping_ratio > 25:
        recommendations.append({
            'priority': '高',
            'title': '文创购物升级',
            'detail': f'购物消费占比{shopping_ratio:.1f}%，建议：①开发灵山IP文创产品（大佛手印、梵宫琉璃系列）；②在梵宫/大佛脚下设置精品文创店；③引入AR互动购物体验。'
        })
    
    # 洞察6：满意度提升
    if avg_satisfaction < 4.0:
        recommendations.append({
            'priority': '中',
            'title': '整体满意度提升',
            'detail': f'平均满意度仅{avg_satisfaction:.2f}分，建议：①优化九龙灌浴演出时间间隔；②完善景区标识与导览系统；③增加休息区与遮阴设施；④强化梵宫艺术展示解说。'
        })
    
    # 洞察7：年轻客群
    young_count = sum(1 for r in records if r['age'] < 35)
    young_ratio = young_count / total * 100 if total > 0 else 0
    if young_ratio < 30:
        recommendations.append({
            'priority': '中',
            'title': '年轻客群拓展',
            'detail': f'18-35岁游客仅占{young_ratio:.1f}%，建议：①推出"灵山夜游"灯光秀；②开发禅意网红打卡点；③与社交媒体联动推出话题活动；④增加梵宫穹顶AR互动体验。'
        })
    
    # 洞察8：停留时长
    long_stay = sum(1 for r in records if r['stay_duration'] >= 8)
    long_stay_ratio = long_stay / total * 100 if total > 0 else 0
    recommendations.append({
        'priority': '低',
        'title': '延长游客停留时长',
        'detail': f'停留8小时以上游客占{long_stay_ratio:.1f}%，建议：①推出"灵山+拈花湾"联票优惠；②增设夜间禅修体验项目；③开发灵山精舍禅意住宿套餐。'
    })
    
    return {
        'code': 200,
        'data': {
            'insights': insights,
            'recommendations': recommendations,
            'avg_total_cost': avg_total,
            'avg_satisfaction': avg_satisfaction,
            'food_ratio': round(food_ratio, 1),
            'shopping_ratio': round(shopping_ratio, 1),
            'high_sat_ratio': round(high_sat_ratio, 1),
            'high_cost_low_sat_count': high_cost_low_sat,
            'young_visitor_ratio': round(young_ratio, 1),
        }
    }


# ===================== 9. CSV上传与筛选 =====================
def extract_lingsan_data(filepath: str, output_csv: str = None, output_json: str = None) -> Dict[str, Any]:
    """从上传的全量数据CSV中筛选灵山景区数据"""
    if output_csv is None:
        output_csv = DEFAULT_CSV
    if output_json is None:
        output_json = DEFAULT_JSON
    
    extracted = []
    all_records = 0
    
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                all_records += 1
                attraction = row.get('attraction_name', '') or row.get('scenic_spot', '') or ''
                if any(kw in attraction for kw in LINSAN_KEYWORDS):
                    # 统一字段映射
                    record = {
                        'tourist_id': row.get('tourist_id', '') or row.get('user_id', ''),
                        'user_nickname': row.get('user_nickname', '') or row.get('name', ''),
                        'age': row.get('age', 0),
                        'gender': row.get('gender', ''),
                        'attraction_name': attraction,
                        'attraction_content': row.get('attraction_content', '') or row.get('description', ''),
                        'attraction_type': row.get('attraction_type', '') or row.get('spot_type', ''),
                        'visit_date': row.get('visit_date', ''),
                        'stay_duration': row.get('stay_duration', 0),
                        'ticket_cost': row.get('ticket_cost', 0),
                        'food_cost': row.get('food_cost', 0),
                        'shopping_cost': row.get('shopping_cost', 0),
                        'transport_cost': row.get('transport_cost', 0),
                        'entertainment_cost': row.get('entertainment_cost', 0),
                        'total_cost': row.get('total_cost', 0),
                        'group_size': row.get('group_size', 0),
                        'satisfaction': row.get('satisfaction', 0),
                    }
                    extracted.append(record)
    except Exception as e:
        return {'code': 500, 'message': f'解析CSV失败: {str(e)}'}
    
    if not extracted:
        return {'code': 404, 'message': '未在数据中找到灵山景区相关记录，请检查数据是否包含灵山大佛/灵山胜境/拈花湾等关键词'}
    
    # 写入CSV
    fieldnames = ['tourist_id', 'user_nickname', 'age', 'gender', 'attraction_name', 
                  'attraction_content', 'attraction_type', 'visit_date', 'stay_duration',
                  'ticket_cost', 'food_cost', 'shopping_cost', 'transport_cost', 
                  'entertainment_cost', 'total_cost', 'group_size', 'satisfaction']
    
    try:
        with open(output_csv, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in extracted:
                writer.writerow(r)
    except Exception as e:
        return {'code': 500, 'message': f'写入CSV失败: {str(e)}'}
    
    # 写入JSON（保留原JSON字段名格式）
    json_records = []
    for r in extracted:
        json_records.append({
            'user_id': r['tourist_id'],
            'name': r['user_nickname'],
            'age': r['age'],
            'gender': r['gender'],
            'scenic_spot': r['attraction_name'],
            'description': r['attraction_content'],
            'spot_type': r['attraction_type'],
            'visit_date': r['visit_date'],
            'stay_duration': r['stay_duration'],
            'ticket_cost': r['ticket_cost'],
            'food_cost': r['food_cost'],
            'shopping_cost': r['shopping_cost'],
            'transport_cost': r['transport_cost'],
            'entertainment_cost': r['entertainment_cost'],
            'total_cost': r['total_cost'],
            'group_size': r['group_size'],
            'satisfaction': r['satisfaction'],
        })
    
    try:
        with open(output_json, 'w', encoding='utf-8') as f:
            json.dump(json_records, f, ensure_ascii=False, indent=2)
    except Exception as e:
        return {'code': 500, 'message': f'写入JSON失败: {str(e)}'}
    
    return {
        'code': 200,
        'message': f'成功从 {all_records} 条记录中提取 {len(extracted)} 条灵山景区数据',
        'data': {
            'total_records': all_records,
            'extracted_count': len(extracted),
            'output_csv': output_csv,
            'output_json': output_json,
        }
    }
