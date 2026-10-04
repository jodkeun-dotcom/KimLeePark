"""Prepare KMA ASOS daily weather (CP949, Korean headers) for the daily card join."""
import argparse
from pathlib import Path
import pandas as pd

# 기상자료개방포털 ASOS 일자료 원본 열 → 영문 snake_case
COLUMNS = {
    '지점': 'station_id', '지점명': 'station_name', '일시': 'date',
    '평균기온(°C)': 'temp_avg_c', '최저기온(°C)': 'temp_min_c', '최저기온 시각(hhmi)': 'temp_min_time',
    '최고기온(°C)': 'temp_max_c', '최고기온 시각(hhmi)': 'temp_max_time',
    '강수 계속시간(hr)': 'precip_duration_hr',
    '10분 최다 강수량(mm)': 'precip_max_10min_mm', '10분 최다강수량 시각(hhmi)': 'precip_max_10min_time',
    '1시간 최다강수량(mm)': 'precip_max_1h_mm', '1시간 최다 강수량 시각(hhmi)': 'precip_max_1h_time',
    '일강수량(mm)': 'precip_mm',
    '최대 순간 풍속(m/s)': 'wind_gust_max_ms', '최대 순간 풍속 풍향(16방위)': 'wind_gust_dir_deg',
    '최대 순간풍속 시각(hhmi)': 'wind_gust_time',
    '최대 풍속(m/s)': 'wind_max_ms', '최대 풍속 풍향(16방위)': 'wind_max_dir_deg', '최대 풍속 시각(hhmi)': 'wind_max_time',
    '평균 풍속(m/s)': 'wind_avg_ms', '풍정합(100m)': 'wind_run_100m', '최다풍향(16방위)': 'wind_dir_mode_deg',
    '평균 이슬점온도(°C)': 'dew_point_avg_c',
    '최소 상대습도(%)': 'humidity_min_pct', '최소 상대습도 시각(hhmi)': 'humidity_min_time',
    '평균 상대습도(%)': 'humidity_avg_pct', '평균 증기압(hPa)': 'vapor_pressure_avg_hpa',
    '일 최심신적설(cm)': 'new_snow_max_cm', '일 최심신적설 시각(hhmi)': 'new_snow_max_time',
    '일 최심적설(cm)': 'snow_depth_max_cm', '일 최심적설 시각(hhmi)': 'snow_depth_max_time',
    '합계 3시간 신적설(cm)': 'new_snow_3h_sum_cm',
    '평균 전운량(1/10)': 'cloud_total_avg', '평균 중하층운량(1/10)': 'cloud_low_mid_avg',
    '기사': 'remarks', '안개 계속시간(hr)': 'fog_duration_hr',
}
STATION_REGION = {101: '강원 춘천시'}  # 카드 region 값과 동일하게 맞춤


def read_raw(source, encoding='cp949'):
    return pd.read_csv(source, encoding=encoding)


def prepare(source, output, encoding='cp949'):
    df = read_raw(source, encoding)
    if set(df) != set(COLUMNS):
        raise ValueError(f'Unexpected ASOS columns: {sorted(set(df) ^ set(COLUMNS))}')
    df = df.rename(columns=COLUMNS)[list(COLUMNS.values())]
    df['region'] = df.station_id.map(STATION_REGION)
    if df.region.isna().any():
        raise ValueError('Station without region mapping')
    df['date'] = pd.to_datetime(df.date, format='%Y-%m-%d', errors='raise')
    if df.duplicated(['date', 'region']).any():
        raise ValueError('Duplicate date/region rows')
    expected = pd.date_range('2025-07-01', '2025-12-31')
    if not df.date.sort_values().reset_index(drop=True).equals(pd.Series(expected, name='date')):
        raise ValueError('Weather must cover every date 2025-07-01~12-31 exactly once')
    times = [c for c in df if c.endswith('_time')]
    df[times] = df[times].astype('Int64')  # hhmi 정수 유지(332 = 03:32)
    df['date'] = df.date.dt.strftime('%Y-%m-%d')
    # 결측(빈칸)은 0으로 채우지 않는다. 강수 빈칸 해석은 docs/weather.md 참고.
    df = df[['date', 'region'] + [c for c in df if c not in ('date', 'region')]]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output, index=False, encoding='utf-8-sig')
    print(f'Saved weather {len(df)} rows: {output}')
    return df


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--encoding', default='cp949')
    args = parser.parse_args()
    prepare(args.input, args.output, args.encoding)
