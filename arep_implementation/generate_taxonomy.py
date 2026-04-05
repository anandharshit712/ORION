import itertools
import random

# Axes
road_types = ["Highway", "Urban Intersection", "Rural Road", "Suburban Street", "Parking Lot"]
weather_conditions = ["Clear Daylight", "Heavy Rain", "Dense Fog", "Pitch Black Night", "Blinding Sun Glare"]
ego_actions = ["Driving Straight at Speed Limit", "Executing Left Turn", "Executing Right Turn", "Merging from On-Ramp", "Performing Evasive Stop"]
actor_types = ["Aggressive Driver (Car)", "Hesitant Pedestrian", "Swerving Cyclist", "Stationary Debris", "Emergency Vehicle"]

# Generate combinations
combinations = list(itertools.product(road_types, weather_conditions, ego_actions, actor_types))
random.seed(42)
selected_scenarios = random.sample(combinations, 200)

with open("ORION_SCENARIO_TAXONOMY.md", "w", encoding="utf-8") as f:
    f.write("# ORION Platform: Autonomous Driving Scenario Taxonomy\n\n")
    
    f.write("## 1. The ORION Parameterization Engine: From 200 to Infinity\n")
    f.write("While this document defines **200 distinct baseline scenario classes**, the true power of the ORION platform lies in **Parameterization**. We do not hardcode every single test. Instead, we use these 200 base classes as templates.\n\n")
    f.write("By mapping continuous variables onto these templates, we generate infinite variants. For example, for a single scenario class, ORION dynamically alters:\n")
    f.write("- **Adversary Speed:** 10 km/h to 120 km/h\n")
    f.write("- **Time to Collision (TTC) bounds:** 1.0s to 5.0s\n")
    f.write("- **Weather Intensity/Friction:** 0.2 (Icy) to 0.9 (Dry)\n")
    f.write("- **Sensor Degradation Noise:** 0% to 50% loss\n\n")
    
    f.write("## 2. Dimensional Axes Matrix\n")
    f.write("The following 200 scenarios were formulated by crossing 4 primary phenomenological axes:\n")
    f.write("1. **Road Topology:** Highway, Urban Intersection, Rural, Suburban, Parking\n")
    f.write("2. **Weather/Lighting:** Clear, Rain, Fog, Night, Glare\n")
    f.write("3. **Ego Maneuver:** Straight, Turn, Merge, Evasive\n")
    f.write("4. **Adversary Type:** Aggressive Car, Pedestrian, Cyclist, Debris, Emergency\n\n")
    
    f.write("## 3. The ORION 200 Base Scenarios Catalog\n\n")
    
    # Categorize by Road Type for readability
    scenario_idx = 1
    for road in road_types:
        f.write(f"### {road} Scenarios\n")
        f.write("| ID | Ego Maneuver | Adversary Interaction | Environmental Factor |\n")
        f.write("|----|-------------|----------------------|----------------------|\n")
        
        road_scenarios = [s for s in selected_scenarios if s[0] == road]
        for s in road_scenarios:
            f.write(f"| SCN-{scenario_idx:03d} | {s[2]} | {s[3]} | {s[1]} |\n")
            scenario_idx += 1
        f.write("\n")
        
    f.write("---\n*End of Taxonomy Document. Compiled by ORION Engine.*")
