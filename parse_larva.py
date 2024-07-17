import sc2reader
import matplotlib.pyplot as plt
import plotly.graph_objs as go
from plotly.offline import plot
from plotly.subplots import make_subplots
import plotly.io as pio
from PIL import Image
import io
import pandas as pd

def player_info(replay_file):
    replay = sc2reader.load_replay(replay_file, load_map=False)
    players_info = []

    for player in replay.players:
        players_info.append({
            "index": player.pid - 1,
            "name": player.name,
            "race": player.play_race
        })

    return players_info


def is_zvz(player_info_list):
    if len(player_info_list) == 2 and all(player['race'] == 'Zerg' for player in player_info_list):
        return True
    else:
        return False


def frame_to_realtime(event_frame):
    return event_frame / 22.4


def process_replay(replay_file, player_index=None):
    replay = sc2reader.load_replay(replay_file, load_map=True)
    larva_born_dict = {}    
    larva_died_dict = {}
    supply_data = {}
    max_supply_data = {}
    player_name = None

    if player_index is not None:
        player_name = replay.players[player_index - 1].name
    else:
        for player in replay.players:
            if player.play_race == 'Zerg':
                player_name = player.name
                player_index = player.pid
                break

    for event in replay.events:
        if isinstance(event, sc2reader.events.tracker.UnitBornEvent) and event.unit_type_name == 'Larva':
            if event.control_pid == replay.players[player_index - 1].pid:
                larva_born_dict[event.unit_id] = frame_to_realtime(event.frame)

        elif isinstance(event, sc2reader.events.tracker.UnitTypeChangeEvent) and event.unit_id in larva_born_dict and event.unit_type_name == 'Egg':
            larva_died_dict[event.unit_id] = frame_to_realtime(event.frame)

        elif isinstance(event, sc2reader.events.tracker.UnitDiedEvent) and event.unit_id in larva_born_dict and event.unit_id not in larva_died_dict:
            larva_died_dict[event.unit_id] = frame_to_realtime(event.frame)

        if event.name == 'PlayerStatsEvent' and event.player.pid == replay.players[player_index - 1].pid:
            time_in_seconds = frame_to_realtime(event.frame)
            supply_data[time_in_seconds] = event.food_used
            max_supply_data[time_in_seconds] = event.food_made

    return larva_born_dict, larva_died_dict, player_name, supply_data, max_supply_data


def calculate_cumulative_total_larva(born_dict):
    larva_count = {}
    cumulative_count = 0

    times = list(born_dict.values())
    
    minute_marker = 0
    time_index = 0
    
    while time_index < len(times) and minute_marker <= max(times):
        while time_index < len(times) and times[time_index] <= minute_marker:
            cumulative_count += 1
            time_index += 1
        
        larva_count[minute_marker // 1] = cumulative_count

        minute_marker += 1
    
    return larva_count


def aggregate_larva_lifespans(born_dict, died_dict, interval_length=15):
    lifespans_per_interval = {}
    max_time = max(died_dict.values(), default=0)
    
    for current_time in range(0, int(max_time) + interval_length, interval_length):
        total_lifespan = 0
        larva_count = 0
        for unit_id, born_time in born_dict.items():
            if current_time <= born_time < current_time + interval_length:
                died_time = died_dict.get(unit_id, float('inf'))
                if died_time > born_time:
                    lifespan = died_time - born_time
                    total_lifespan += lifespan
                    larva_count += 1
        average_lifespan = (total_lifespan / larva_count) if larva_count else 0
        lifespans_per_interval[current_time] = average_lifespan

    return lifespans_per_interval


def calculate_idle_larva_counts(born_dict, died_dict, start_second, end_second, idle_threshold):
    idle_larva_count_per_second = {}
    max_time = max(died_dict.values(), default=0)
    
    for current_time in range(start_second, int(min(end_second, max_time)) + 1):
        idle_larva_count = 0
        for unit_id, born_time in born_dict.items():
            died_time = died_dict.get(unit_id, float('inf'))
            if born_time + idle_threshold <= current_time <= died_time:
                idle_larva_count += 1
        idle_larva_count_per_second[current_time] = idle_larva_count

    return idle_larva_count_per_second


def idle_larva_per_phase(born_dict, died_dict, phase_intervals):
    idle_counts = {}
    for phase, (start_minute, end_minute, idle_threshold) in phase_intervals.items():
        start_second = int(start_minute * 60)
        end_second = int(end_minute * 60)
        idle_counts[phase] = calculate_idle_larva_counts(born_dict, died_dict, start_second, end_second, idle_threshold)
    return idle_counts


def plotly_create_figure(benchmark_data, comparison_data, title, y_axis_label, benchmark_name=None, comparison_name=None, window=None, x_range=None, y_range=None):
    traces = []
    colors = ['LightSkyBlue', 'LightCoral']

    def create_trace(data, name, color, window=None):
        series = pd.Series(data)
        if window:
            series = series.rolling(window=window).mean()
        return go.Scatter(
            x=series.index / 60,
            y=series.values,
            mode='lines',
            name=name,
            line=dict(width=2, color=color)
        )

    traces.append(create_trace(benchmark_data, benchmark_name, colors[0], window))
    if comparison_data:
        traces.append(create_trace(comparison_data, comparison_name, colors[1], window))

    layout = go.Layout(
        title=title,
        titlefont=dict(color='White', size=30),
        paper_bgcolor='Black',
        plot_bgcolor='Black',
        xaxis=dict(
            title='Time (minutes)',
            titlefont=dict(color='White', size=20),
            tickfont=dict(color='White', size=16),
            showgrid=True,
            gridwidth=1,
            gridcolor='Gray',
            range=[0, x_range] if x_range else None
        ),
        yaxis=dict(
            title=y_axis_label,
            titlefont=dict(color='White', size=20),
            tickfont=dict(color='White', size=16),
            showgrid=True,
            gridwidth=1,
            gridcolor='Gray',
            range=[0, y_range] if y_range else None
        ),
        legend=dict(
            x=0,
            y=1,
            borderwidth=1,
            bgcolor='Black',
            font=dict(color='White', size=26)
        ),
        height=750,
        width=1400
    )
    
    fig = go.Figure(data=traces, layout=layout)
    fig.update_layout(showlegend=len(traces) > 1)

    return fig


def all_in(comparison_replay, benchmark_replay=None, player=None, benchmark_player=None):
    if player == 'not_zvz':
        player = None
    if benchmark_player == 'not_zvz':
        benchmark_player = None

    if benchmark_replay is None:
        benchmark_replay = comparison_replay
        if player is not None:
            benchmark_player = player

    if player is not None:
        benchmark_born, benchmark_died, benchmark_name, benchmark_supply, benchmark_max_supply = process_replay(benchmark_replay, benchmark_player)
        comparison_born, comparison_died, comparison_name, comparison_supply, comparison_max_supply = process_replay(comparison_replay, player)        
    else:
        benchmark_born, benchmark_died, benchmark_name, benchmark_supply, benchmark_max_supply = process_replay(benchmark_replay)
        comparison_born, comparison_died, comparison_name, comparison_supply, comparison_max_supply = process_replay(comparison_replay)

    if benchmark_name == comparison_name and benchmark_born != comparison_born:
        benchmark_name += f" ({benchmark_replay})"
        comparison_name += f" ({comparison_replay})"

    benchmark_avg_lifespan = aggregate_larva_lifespans(benchmark_born, benchmark_died, interval_length=15)
    comparison_avg_lifespan = aggregate_larva_lifespans(comparison_born, comparison_died, interval_length=15)

    phase_intervals = {
        'Early Game': (0, 7, 5)
    }

    benchmark_idle_counts = idle_larva_per_phase(benchmark_born, benchmark_died, phase_intervals)
    comparison_idle_counts = idle_larva_per_phase(comparison_born, comparison_died, phase_intervals)

    benchmark_length = max(benchmark_died.values(), default=0) / 60
    comparison_length = max(comparison_died.values(), default=0) / 60
    x_range = min(benchmark_length, comparison_length)

    figures = []
    figures.append(plotly_create_figure(benchmark_avg_lifespan, comparison_avg_lifespan, 'Average Larva Lifespan Per Minute Comparison', 'Average Lifespan (seconds)', benchmark_name, comparison_name, x_range=x_range, y_range=30))
    
    early_game_title = 'Average Idle Larva During Early Game: >5 Second idle time'
    figures.append(plotly_create_figure(benchmark_idle_counts['Early Game'], comparison_idle_counts['Early Game'], early_game_title, 'Average Idle Larva Count', benchmark_name, comparison_name, window=15, x_range=min(7, x_range)))

    benchmark_total_count = calculate_cumulative_total_larva(benchmark_born)
    comparison_total_count = calculate_cumulative_total_larva(comparison_born)
    x_range_seconds = min(max(benchmark_total_count.keys(), default=0), max(comparison_total_count.keys(), default=0)) / 60

    figures.append(plotly_create_figure(benchmark_supply, benchmark_max_supply, 'Benchmark Supply Over Time', 'Supply Count', f"{benchmark_name} - Current Supply", f"{benchmark_name} - Max Supply", x_range=x_range, y_range=200))
    figures.append(plotly_create_figure(comparison_supply, comparison_max_supply, 'Comparison Supply Over Time', 'Supply Count', f"{comparison_name} - Current Supply", f"{comparison_name} - Max Supply", x_range=x_range, y_range=200))
    
    figures.append(plotly_create_figure(benchmark_total_count, comparison_total_count, 'Total Larva Spawned', 'Larva Count', benchmark_name, comparison_name, x_range=x_range_seconds))

    imgs = [Image.open(io.BytesIO(fig.to_image(format="png"))) for fig in figures]

    num_columns = 2
    num_rows = len(imgs) // num_columns + (len(imgs) % num_columns > 0)

    column_widths = [max(img.width for img in imgs[i::num_columns]) for i in range(num_columns)]
    total_width = sum(column_widths)
    row_heights = [max(imgs[i::num_columns], key=lambda im: im.height).height for i in range(0, num_rows * num_columns, num_columns)]
    total_height = sum(row_heights)

    combined_image = Image.new('RGB', (total_width, total_height))

    x_offset = 0
    for col in range(num_columns):
        y_offset = 0
        for row in range(num_rows):
            img_index = row * num_columns + col
            if img_index < len(imgs):
                combined_image.paste(imgs[img_index], (x_offset, y_offset))
                y_offset += imgs[img_index].height
        x_offset += column_widths[col]

    image_bytes = io.BytesIO()
    combined_image.save(image_bytes, format='PNG')
    image_bytes.seek(0)

    return image_bytes.getvalue()