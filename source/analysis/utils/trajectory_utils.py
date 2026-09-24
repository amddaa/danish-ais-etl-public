import numpy as np
from scipy.signal import medfilt
from datetime import datetime

EARTH_RADIUS_M = 6_371_000
DEFAULT_MAX_SPEED_KNOTS = 50.0
DEFAULT_SIMPLIFY_TOLERANCE_M = 100.0


def haversine_distance(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, [lon1, lat1, lon2, lat2])

    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = np.sin(dlat / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin(dlon / 2) ** 2
    c = 2 * np.arcsin(np.sqrt(a))
    return c * EARTH_RADIUS_M


def clean_trajectory(points, max_speed_knots=DEFAULT_MAX_SPEED_KNOTS):
    """
    Cleans AIS trajectory based on:
    1. Spatial bounds (lat: -90 to 90, lon: -180 to 180)
    2. Zero-point filtering (0,0)
    3. Jump detection (unphysical speed between points)
    
    points: list of [lat, lon, timestamp, sog, ...]
    """
    if not points:
        return []
    
    # 1. Basic filtering (bounds and zeros)
    cleaned = []
    for p in points:
        lat, lon = p[0], p[1]
        # Drop points with exact 0 longitude as they often represent invalid GPS data (e.g., 89.0, 0.0)
        if lon == 0:
            continue
        if not (-90 < lat < 90 and -180 < lon < 180):
            continue
        cleaned.append(p)
    
    if not cleaned:
        return []

    # 2. Jump detection (Speed-based)
    # We iterate and keep only points that are reachable from the previous valid point
    final_points = [cleaned[0]]
    for i in range(1, len(cleaned)):
        prev = final_points[-1]
        curr = cleaned[i]
        
        # Calculate speed between prev and curr
        dist = haversine_distance(prev[1], prev[0], curr[1], curr[0]) # meters
        
        # Parse timestamps if they are strings
        t1 = prev[2] if isinstance(prev[2], datetime) else datetime.fromisoformat(str(prev[2]).replace('Z', '+00:00'))
        t2 = curr[2] if isinstance(curr[2], datetime) else datetime.fromisoformat(str(curr[2]).replace('Z', '+00:00'))
        
        dt = (t2 - t1).total_seconds()
        
        if dt <= 0:
            continue # Skip duplicates or time-reversed points
            
        speed_mps = dist / dt
        speed_knots = speed_mps * 1.94384
        
        if speed_knots <= max_speed_knots:
            final_points.append(curr)
        # If speed is too high, we assume 'curr' is a jump/error and skip it
        
    return final_points

def apply_median_filter(points, window_size=5):
    """
    Applies median filter to lat/lon to remove jitter.
    points: list of [lat, lon, ...]
    """
    if len(points) < window_size:
        return points
    
    lats = np.array([p[0] for p in points])
    lons = np.array([p[1] for p in points])
    
    # medfilt requires odd window size
    if window_size % 2 == 0:
        window_size += 1
        
    smooth_lats = medfilt(lats, kernel_size=window_size)
    smooth_lons = medfilt(lons, kernel_size=window_size)
    
    new_points = []
    for i in range(len(points)):
        p = list(points[i])
        p[0] = float(smooth_lats[i])
        p[1] = float(smooth_lons[i])
        new_points.append(p)
        
    return new_points

def perpendicular_distance(point, start, end):
    """Fast perpendicular distance calculation without numpy overhead."""
    x, y = point[0], point[1]
    x1, y1 = start[0], start[1]
    x2, y2 = end[0], end[1]
    
    # Distance from point (x,y) to line (x1,y1)-(x2,y2)
    dx = x2 - x1
    dy = y2 - y1
    
    if dx == 0 and dy == 0:
        return ((x - x1)**2 + (y - y1)**2)**0.5
        
    # Standard formula for distance from point to line
    return abs(dy * x - dx * y + x2 * y1 - y2 * x1) / (dx**2 + dy**2)**0.5

def douglas_peucker_indices(points, tolerance):
    """
    Douglas-Peucker algorithm returning indices of kept points.
    Iterative implementation to avoid recursion depth issues.
    """
    n = len(points)
    if n < 3:
        return list(range(n))
        
    kept = [False] * n
    kept[0] = True
    kept[n-1] = True
    
    # Stack of (start, end) ranges to process
    stack = [(0, n-1)]
    
    while stack:
        start, end = stack.pop()
        
        dmax = 0
        index = 0
        
        for i in range(start + 1, end):
            d = perpendicular_distance(points[i], points[start], points[end])
            if d > dmax:
                index = i
                dmax = d
                
        if dmax > tolerance:
            kept[index] = True
            # Push both halves to the stack
            stack.append((start, index))
            stack.append((index, end))
            
    return [i for i, is_kept in enumerate(kept) if is_kept]

def simplify_trajectory(points, tolerance_meters=DEFAULT_SIMPLIFY_TOLERANCE_M):
    """
    Wrapper for Douglas-Peucker using meters for tolerance.
    """
    if len(points) < 3:
        return points
    
    tolerance_deg = tolerance_meters / 111111.0
    coords = np.array([[p[0], p[1]] for p in points])
    
    kept_indices = douglas_peucker_indices(coords, tolerance_deg)
    return [points[i] for i in kept_indices]
