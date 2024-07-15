import sc2reader
import matplotlib.pyplot as plt
import plotly.graph_objs as go
from plotly.offline import plot
from plotly.subplots import make_subplots
import plotly.io as pio
from PIL import Image
import io

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
    player_name = None

    if player_index is not None:
        player_name = replay.players[player_index - 1].name
    else:
        for player in replay.players:
            if player.play_race == 'Zerg':
                player_name = player.name
                break

    for event in replay.events:
        if isinstance(event, sc2reader.events.tracker.UnitBornEvent) and event.unit_type_name == 'Larva':
            if player_index is not None:
                if event.control_pid == replay.players[player_index - 1].pid:
                    larva_born_dict[event.unit_id] = frame_to_realtime(event.frame)
            else:
                larva_born_dict[event.unit_id] = frame_to_realtime(event.frame)

        elif isinstance(event, sc2reader.events.tracker.UnitDiedEvent) and event.unit_id in larva_born_dict:
            larva_died_dict[event.unit_id] = frame_to_realtime(event.frame)

    return larva_born_dict, larva_died_dict, player_name
    



def average_larva_lifespan_per_interval(born_dict, died_dict, interval_length=60):
    average_lifespan_per_interval = {}
    max_time = max(died_dict.values(), default=0)
    for start_time in range(0, int(max_time) + interval_length, interval_length):
        end_time = start_time + interval_length
        total_lifespan = 0
        larva_count = 0
        for unit_id, born_time in born_dict.items():
            if start_time <= born_time < end_time:
                died_time = died_dict.get(unit_id, float('inf'))
                if died_time > born_time:
                    lifespan = min(died_time, end_time) - born_time
                    total_lifespan += lifespan
                    larva_count += 1
        average_lifespan = (total_lifespan / larva_count) if larva_count else 0
        average_lifespan_per_interval[start_time // 60] = average_lifespan
    return average_lifespan_per_interval

def average_idle_larva_per_phase(born_dict, died_dict, start_minute, end_minute, idle_threshold):
    idle_larva_count_per_interval = {}
    max_time = max(died_dict.values(), default=0)
    
    for current_time in range(int(start_minute * 60), int(min(end_minute * 60, max_time)) + 1):
        idle_larva_count = 0
        for unit_id, born_time in born_dict.items():
            died_time = died_dict.get(unit_id, float('inf'))
            if born_time + idle_threshold <= current_time <= died_time:
                idle_larva_count += 1

        current_minute = current_time // 60
        idle_larva_count_per_interval[current_minute] = idle_larva_count_per_interval.get(current_minute, 0) + idle_larva_count

    for minute in idle_larva_count_per_interval:
        idle_larva_count_per_interval[minute] /= 60

    return idle_larva_count_per_interval


def calculate_idle_larva_counts(born_dict, died_dict, phase_intervals):
    idle_counts = {}
    for phase, (start_minute, end_minute, idle_threshold) in phase_intervals.items():
        idle_counts[phase] = average_idle_larva_per_phase(born_dict, died_dict, start_minute, end_minute, idle_threshold)
    return idle_counts

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
        
        larva_count[minute_marker // 60] = cumulative_count

        minute_marker += 60
    
    return larva_count


def plotly_create_figure(benchmark_data, comparison_data, title, y_axis_label, benchmark_name=None, comparison_name=None):
    traces = []
    colors = ['LightSkyBlue', 'LightCoral']

    traces.append(go.Scatter(
        x=list(benchmark_data.keys()),
        y=list(benchmark_data.values()),
        mode='lines+markers',
        name=benchmark_name if benchmark_name else 'Benchmark',
        marker=dict(size=8, line=dict(width=2), color=colors[0]),
        line=dict(width=2, color=colors[0])
    ))

    if comparison_data is not None and comparison_data != benchmark_data:
        traces.append(go.Scatter(
            x=list(comparison_data.keys()),
            y=list(comparison_data.values()),
            mode='lines+markers',
            name=comparison_name if comparison_name else 'Comparison',
            marker=dict(size=8, line=dict(width=2), color=colors[1]),
            line=dict(width=2, color=colors[1])
        ))

    layout = go.Layout(
        title=title,
        titlefont=dict(color='White',size=30),
        paper_bgcolor='Black',
        plot_bgcolor='Black',
        xaxis=dict(
            title='Time (minutes)',
            titlefont=dict(color='White',size=20),
            tickfont=dict(color='White',size=16),
            showgrid=True,
            gridwidth=1,
            gridcolor='Gray',
        ),
        yaxis=dict(
            title=y_axis_label,
            titlefont=dict(color='White',size=20),
            tickfont=dict(color='White',size=16),
            showgrid=True,
            gridwidth=1,
            gridcolor='Gray',
        ),
        legend=dict(
            x=0,
            y=1,
            borderwidth=1,
            bgcolor='Black',
            font=dict(color='White', size=26)  #Increased legend font size
        ),
        height=750,
        width=1400
    )
    
    fig = go.Figure(data=traces, layout=layout)

    #Conditionally show or hide the legend based on the number of replays
    fig.update_layout(showlegend=len(traces) > 1)

    return fig

def remove_last_entry(data_dict):
    if data_dict:
        sorted_keys = sorted(data_dict.keys())
        last_key = sorted_keys[-1]
        del data_dict[last_key]
    return data_dict

def all_in(comparison_replay, benchmark_replay=None,player=None, benchmark_player=None):

    #ensures that calls from !compare when mixing non-zvz and zvz replays do not call the incorrect player index. A workaround to stop adding more complexity to the already cumbersome state logic of context{}
    if player == 'not_zvz':
        player = None
    if benchmark_player == 'not_zvz':
        player = None

    if benchmark_replay is None:
        benchmark_replay = comparison_replay
        if player is not None:
            benchmark_player = player
        
    if player:
        benchmark_born, benchmark_died, benchmark_name = process_replay(benchmark_replay, benchmark_player)
        comparison_born, comparison_died, comparison_name = process_replay(comparison_replay, player)        
    else:
        benchmark_born, benchmark_died, benchmark_name = process_replay(benchmark_replay)
        comparison_born, comparison_died, comparison_name = process_replay(comparison_replay)

    benchmark_avg_lifespan = remove_last_entry(average_larva_lifespan_per_interval(benchmark_born, benchmark_died))
    comparison_avg_lifespan = remove_last_entry(average_larva_lifespan_per_interval(comparison_born, comparison_died))

    phase_intervals = {
        'Early Game': (0, 7, 5),
        'Late Game': (7, 15, 15)
    }

    benchmark_idle_counts = calculate_idle_larva_counts(benchmark_born, benchmark_died, phase_intervals)
    comparison_idle_counts = calculate_idle_larva_counts(comparison_born, comparison_died, phase_intervals)

    figures = []
    figures.append(plotly_create_figure(benchmark_avg_lifespan, comparison_avg_lifespan, 'Average Larva Lifespan Per Minute Comparison', 'Average Lifespan (seconds)',benchmark_name,comparison_name))
    
    early_game_title = 'Average Idle Larva During Early Game: >5 Second idle time'
    late_game_title = 'Average Idle Larva During Late Game: >15 Second Idle Time'
    
    figures.append(plotly_create_figure(benchmark_idle_counts['Early Game'], comparison_idle_counts['Early Game'], early_game_title, 'Average Idle Larva Count',benchmark_name,comparison_name))
    figures.append(plotly_create_figure(benchmark_idle_counts['Late Game'], comparison_idle_counts['Late Game'], late_game_title, 'Average Idle Larva Count',benchmark_name,comparison_name))

    benchmark_total_count = calculate_cumulative_total_larva(benchmark_born)
    comparison_total_count = calculate_cumulative_total_larva(comparison_born)

    figures.append(plotly_create_figure(benchmark_total_count,comparison_total_count,'Total Larva Spawned','Larva Count',benchmark_name, comparison_name))

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

