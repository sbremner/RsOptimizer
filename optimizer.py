#!/usr/bin/env python3
import copy
import inspect
import random
import math
import ast

def adjust_adrenaline(pstate, action):
    # Adjust adrenaline as appropriate
    if hasattr(action, "adrenaline_change") and action.adrenaline_change is not None:
        if action.adrenaline_change == -100 and pstate.use_ringofvigour == True:
            # We gain 10 adrenaline if we are using ring of vigour
            actual_change = -90
        elif action.adrenaline_change == -15 and \
                pstate.use_ASR and pstate.use_prng:
            actual_change = 0 if random.random() <= .1 else -15
        else:
            actual_change = action.adrenaline_change
        
        pstate.adrenaline += actual_change
        
        if actual_change > 0:
            pstate.gained_adrenaline += actual_change
        else:
            pstate.spent_adrenaline += abs(actual_change)
        
        # Make sure we don't go above 100 adrenaline
        if pstate.adrenaline > 100:
            pstate.excess_adrenaline += pstate.adrenaline - 100
            pstate.adrenaline = 100

            
def apply_mods(pstate, action):
    # If we have a mod, apply mod to the pstate
    if hasattr(action, "mod") and type(action.mod) == Modifier:
        mod = copy.deepcopy(action.mod)
        mod.reset()
        
        if mod.name not in[m.name for m in pstate.active_mods if m.is_unqiue]:
            pstate.active_mods.append(mod)
        else:
            # We should find the mod and reset it if it was just rewned
            for i in range(0, len(pstate.active_mods)):
                if pstate.active_mods[i].name == mod.name:
                    pstate.active_mods[i].reset()

        
def update_buddies(pstate, action):
    # Update any of our buddy actions that share a cooldown with us
    # (useful for testing variations of stopping multi-tick abilities)
    if action.shares_cooldown():
        for action_name in action.buddy_actions:
            i = Action.find_by_name(action_name, action_list=pstate.actions)
            if i is not None:
                pstate.actions[i].last_used = 0
            
            
def register_action_value(pstate, action):   
    # Update the appropriate action to reflect the value for this usage.
    # Later, we can use the total_used_value / times_used to compute the
    # damage per point of adrenaline.
    i = Action.find_by_name(action.name, pstate.actions)
    
    if i is not None:
        pstate.actions[i].total_used_value += pstate.value(action, mod_value_prediction=False)    

            
# Idea: Look at PState value based on total
#   number of choices + total value of choices
#   and use this number to improve heuristic
class PState:
    def __init__(self, actions, adrenaline=0, use_prng=False, use_ringofvigour=False, use_ASR=False):
        self.adrenaline = adrenaline
        self.excess_adrenaline = 0
        self.spent_adrenaline = 0
        self.gained_adrenaline = 0
        self.actions = actions
        self.use_prng = use_prng
        self.active_mods = []
        self.use_ringofvigour = use_ringofvigour
        self.use_ASR = use_ASR
        
        # Track all changes that need to occur
        # on activation of an ability
        self.on_activate = [
            adjust_adrenaline,
            apply_mods,
            update_buddies,
            register_action_value,
        ]
                
    # Normalized Average/Best value used for computing
    # modifier values (average = duration, best = one_time_use)
    # Adjust ticks to find abilities usable within a tick time frame
    def normalized_average_value(self, ticks=3, mod=None, filter=None):
        values = []
        
        # Create a fake pstate that has maximum possible adrenaline gain
        adrenaline_pstate = PState(actions=[], adrenaline=int(self.adrenaline + ((ticks - 3) / 3.0) * 8))
        
        for a in self.actions:
            # Check if we have a filter function that will check if we want
            # to keep this action included (if filter returns False/None, then
            # we skip this action and move on to the next)
            if filter is not None and inspect.isfunction(filter) and \
                not filter(a):
                continue
                
            if a.time_remaining <= ticks and adrenaline_pstate.check_pstate(a):
                val = a.value()
                if mod is not None:
                    val = mod.apply_mod(val)
                    
                values.append(val / a.ticks)
                
        return sum(values) / len(values)
        
    
    def normalized_best_value(self, ticks=3, mod=None, filter=None):       
        current_best_val = 0
        
        for a in self.actions:
            # Check if we have a filter function that will check if we want
            # to keep this action included (if filter returns False/None, then
            # we skip this action and move on to the next)
            if filter is not None and inspect.isfunction(filter) and \
                not filter(a):
                continue
        
            if a.time_remaining <= ticks and self.check_pstate(a):
                val = a.value()                
                if mod is not None and a.modable:
                    val = mod.apply_mod(val)
                
                val = val / a.ticks
                
                if current_best_val < val:
                    current_best_val = val

        return current_best_action

    def tick(self, ticks=3):
        for a in self.actions:
            a.tick(ticks)
            
        for m in self.active_mods:
            m.tick(ticks)
        
        # Filter out all of the mods that are inactive at this point
        # TODO: Check if this is the appropriate way to "remove" items
        #   created by us from a list or if this is a memory problem
        self.active_mods = [m for m in self.active_mods if m.is_active]

    def activate(self, name=None):
        # If the "None" action is activated, we will perform 1 tick
        # to progress the cooldowns of all of our abilities
        if name == None:
            self.tick(1)
            return None
    
        action_i = Action.find_by_name(name, action_list=self.actions)
        
        # Do nothing, we found no action
        if action_i is None:
            print("[!] :: Error - {0} is not a valid action name".format(name))
            return None

        action = self.actions[action_i]
            
        # Trigger activate for the action
        action.activate()

        # Triggar all functions required on_activate
        for f in self.on_activate:
            try:
                f(self, action)
            except Exception as e:
                print("Error: {0}".format(e))
            
        # Perform a tick appropriate for the actions execution duration
        self.tick(action.ticks)

    def get_most_value(self):
        most_value = 0
        action = None
        
        for a in self.actions:
            value = self.value(a) * a.times_used
            
            if action is None or most_value < value:
                most_value = value
                action = a
                
        return action, most_value
        
    def get_most_used(self):
        times_used = 0
        action = None
        
        for a in self.actions:
            if a.times_used > times_used or action is None:
                action = a
                times_used = a.times_used
                
        return action, times_used
        
    def get_greedy_best(self):
        greedy_action = None        
        current_best_val = 0
        current_best_action = None
        
        for a in self.get_available_actions():
            val = self.value(a)
            
            # Update if we have no action, new one is better, or new one
            # is same but has a lower cooldown
            if (current_best_action is None) or \
                (val == current_best_val and a.cooldown < current_best_action.cooldown) or \
                (val > current_best_val):
                current_best_val = val
                current_best_action = a
            
        return current_best_action
       
    def value(self, action, mod_value_prediction=True):
        if action is None:
            return 0
    
        base_value = action.value(prng=self.use_prng)
        
        # For modable actions, apply all active mods to our value
        if action.modable:
            for m in self.active_mods:
                if m.is_active:
                    base_value = m.apply_mod(base_value)
            
        # Perform predictable increase in value from
        # a mod applying to future actions
        if getattr(action, "mod", None) is not None and mod_value_prediction:
            # We will use this filter to make sure we only apply out normalization
            # calculations for modable actions since others wouldn't get adding
            # any value to our current action
            modable_filter = lambda a : getattr(a, "modable", False)
            value_increase = lambda v,m : v - (v / (1 + m))
        
            if action.mod.one_time_use:
                # This gets the value of our next best usable action for one_time_use mods
                next_action_value = self.normalized_best_value(ticks=action.ticks, mod=action.mod, filter=modable_filter)
                # Compute the "increase" in value that our mod is adding and make that value
                # become added to our mod (makes actions with modifiers worth more as they should)
                increase = value_increase(next_action_value, action.mod.multiplier)
            else:
                # Here we are computing mods that have duration
                average_tick_value = self.normalized_average_value(
                    ticks=action.mod.duration, mod=action.mod, filter=modable_filter
                )
                # We can get the total value added by this action's modifier by finding an approximate
                # value per tick added by the modifier and then multiplying by the number of ticks (duration)
                increase = value_increase(average_tick_value, action.mod.multiplier) * action.mod.duration
            
            base_value += increase
            
        return base_value
       
    def get_available_actions(self):
        # If there is an available action that we MUST use, we will look at
        # all of these as our set of "available" actions
        always_use_actions = [
            a for a in self.actions
            if a.always_use == True and a.is_ready() and self.check_pstate(a)
        ]
        
        if len(always_use_actions) > 0:
            return always_use_actions

        actions = []
            
        for a in self.actions:
            if a.is_ready() and self.check_pstate(a):
                actions.append(a)
                
        return actions
        
    def check_pstate(self, action):
        if not inspect.isfunction(action.pstate_check):
            return True

        return action.pstate_check(self) ^ action.negative_pstate_check

class Duration:
    def __init__(self, last_used=0):
        self.last_used = last_used
        self.times_used = 0
        
    def tick(self, ticks=3):
        self.last_used += ticks
        
    def activate(self):
        # Reset out last_used time
        self.last_used = 0
        
        # Increase our counter keep track of times used
        self.times_used += 1

        
class Modifier(Duration):
    def __init__(self, name, multiplier, duration=None, one_time_use=False, is_unqiue=True):
        self.name = name
        self.multiplier = multiplier
        self.duration = duration
        self.one_time_use = one_time_use
        self.is_active = True
        self.is_unqiue = is_unqiue
    
    # Activate shouldn't reset the ability since this is a 
    # modifier, it is duration based and will persist (usage
    # is only considered from the start)
    def activate(self, value):
        # Check if modifier expired but we forgot to remove it
        # (should be removed next tick)
        if not self.is_active:
            return value
    
        if (self.one_time_use and self.is_active) or \
            (self.last_used >= self.duration):
            self.is_active = False
            
        return self.apply_mod(value)

    def tick(self, ticks=3):
        super(Modifier, self).tick(ticks)
        
        # When we tick, check if we need to deactivate this mod
        if self.is_active and (self.last_used >= self.duration):
            self.is_active = False
        
    # This function is ignorant to the state of the modifier
    # Only activate and reset will adjust its state
    def apply_mod(self, value):
        return value + (value * self.multiplier)
        
    def reset(self):
        self.last_used = 0
        self.is_active = True
        
 
class Ability(Duration):
    def __init__(self, min=None, max=None, cooldown=None, ticks=3, \
        pstate_check=None, negative_pstate_check=False, mod=None, modable=True, \
        adrenaline_change=8, accuracy_mod=0, number_of_hits=1, \
        always_use=False, enabled=True, equipment=None):
        
        self.min = float(min if min else (.20 * max))
        self.max = max if max is None else float(max)
        self.ticks = ticks
        self.pstate_check = pstate_check
        self.negative_pstate_check = negative_pstate_check
        self.cooldown = float(cooldown)
        self.mod = mod
        self.modable = modable
        self.adrenaline_change = adrenaline_change
        self.accuracy_mod = accuracy_mod
        self.number_of_hits = number_of_hits
        
        self.always_use = always_use
        self.enabled = enabled
        
        # 2H, DW, Shield
        self.equipment = equipment
        
        self.total_used_value = 0
        
        super(Ability, self).__init__(last_used=cooldown)

    # Can use pseudo-random numbers to simulate
    # real min/max instead of averaging
    def value(self, prng=False, normalize=True):
        # 1. Average min/max or use PRNG
        # 2. Adjust by accuracy_mod
        # 3. Normalize by ticks if requested
        # 4. Multiple by total number of hits
        if prng:
            random.seed()
            val = random.uniform(self.min, self.max)
        else:
            val = (self.min + self.max) / 2.0
            
        val += val * self.accuracy_mod

        if normalize:
            val = val / self.ticks
            
        return val * self.number_of_hits
       
    @property
    def time_remaining(self):
        return self.cooldown - self.last_used
       
    def is_ready(self):
        return self.last_used >= self.cooldown and self.enabled
        
        
class Action(Ability):
    def __init__(self, name, buddy_actions=None, *args, **kwargs):
        self.name = name
        self.buddy_actions = buddy_actions
        super(Action, self).__init__(*args, **kwargs)
        
    def __repr__(self):
        return "{0} ({1})".format(self.name, self.ticks)

    def shares_cooldown(self):
        return self.buddy_actions is not None and len(self.buddy_actions) > 0
        
    @staticmethod
    def find_by_name(name, action_list):
        for i in range(0, len(action_list)):
            if action_list[i].name == name:
                return i
                
        return None


def pstate_threshold(pstate):
    return pstate.adrenaline >= 50


def pstate_threshold_melee(pstate):
    i = Action.find_by_name("Bersker", pstate.actions)
   
    if i is not None and \
        (pstate.actions[i].is_ready() or \
        (((pstate.adrenaline - 15) + (pstate.actions[i].time_remaining * (8 / 3.0))) < 100)):
        return False

    return pstate.adrenaline >= 50
    
    
def pstate_threshold_range(pstate):
    i = Action.find_by_name("Death's Swiftness", pstate.actions)
    
    # Check if using this threshold is going to make it so we can't
    # use Death's Swiftness immediately when it's off CD
    if i is not None and  \
        (pstate.actions[i].is_ready() or \
        (((pstate.adrenaline - 15) + (pstate.actions[i].time_remaining * (8 / 3.0))) < 100)):
        return False

    return pstate.adrenaline >= 50

    
def pstate_ultimate(pstate):
    return pstate.adrenaline == 100


def get_total(actions):
    total = 0
    
    for a in actions:
        total += (a["value"] * a["action"].ticks)
        
    return total
    
def greedy_value(pstate, ticks):
    actions = []
    current_tick = 0
    
    while current_tick <= ticks:
        
        action = pstate.get_greedy_best()
        
        if action is None:
            pstate.tick(1)
            current_tick += 1
            
        mods = [m.name for m in pstate.active_mods if m.is_active]
        
        actions.append({
            "action": action,
            "value": pstate.value(action, mod_value_prediction=False),
            "adrenaline": pstate.adrenaline,
            "mods": "" if len(mods) == 0 else "[{0}]".format(" | ".join(mods))
        })
        
        pstate.activate(getattr(action, "name", None))
        current_tick += 1 if action is None else action.ticks

    return actions
        
def to_ticks(sec):
    return math.ceil(sec / .6)

deaths_swiftness_mod = Modifier(
    name="Death's Swiftness",   # Name to reference the modifier by
    multiplier=.50,             # 50% increase
    duration=to_ticks(sec=30),  # Lasts for 30 seconds
    one_time_use=False          # Lasts full duration, not just until next attack
)

berserk_mod = Modifier(
    name="Berserk",
    multiplier=1.00,
    duration=to_ticks(sec=20),
    one_time_use=False
)

quake_modifier = Modifier(
    name="Quake",
    multiplier=.04, # Roughly a 4% dmg increase (5% dmg debuff for 1 minute)
    duration=to_ticks(sec=60),
    one_time_use=False,
    is_unqiue=True
)

range_2h_actions = [
    Action("Tuska's Wraith", max=110, cooldown=to_ticks(sec=15)),
    Action("Sacrifice", max=100, cooldown=to_ticks(sec=30)),
    
    # TODO: Add real dmg calculations so we can cap the 12k hits
    Action("Shadow Tendrils", min=66, max=500, cooldown=to_ticks(sec=45),
        adrenaline_change= -15, pstate_check=pstate_threshold_range, enabled=True),
    
    Action("Bombardment", max=219, cooldown=to_ticks(sec=30), 
        adrenaline_change= -15, pstate_check=pstate_threshold_range),
    
    Action("Snipe", min=125.0, max=219.0, cooldown=to_ticks(sec=10), ticks=4),
    
    Action("Piercing Shot", max=94, cooldown=to_ticks(sec=3), always_use=True),
    
    Action("Binding Shot", max=100.0, cooldown=to_ticks(sec=15)),
    
    Action("Snapshot", min=(100+100), max=(210+120), cooldown=to_ticks(sec=20),
        adrenaline_change= -15, pstate_check=pstate_threshold_range),
    
    Action("Dazing Shot", max=157, cooldown=to_ticks(sec=5)),
    
    Action("Fragmentation Shot", min=100, max=188, cooldown=to_ticks(sec=15), modable=False),
    
    Action("Rapid Fire", max=94, cooldown=to_ticks(sec=20), number_of_hits=8, ticks=7,
        adrenaline_change= -15, pstate_check=pstate_threshold_range),
    
    Action("Corruption Shot", min=19.8, max=60, cooldown=to_ticks(sec=15),
        number_of_hits=5, modable=False),
    
    Action("Death's Swiftness", min=10, max=20, cooldown=to_ticks(sec=60), number_of_hits=15,
        adrenaline_change= -100, pstate_check=pstate_ultimate, modable=False,
        mod=deaths_swiftness_mod
    ),
]

melee_2h_actions = [
    Action("Tuska's Wraith", max=110, cooldown=to_ticks(sec=15)),
    Action("Sacrifice", max=100, cooldown=to_ticks(sec=30)),

    Action("Cleave", max=188, cooldown=to_ticks(sec=7)),
    
    # Enable this to test sweaty swaps for decimate
    Action("Decimate", max=188, cooldown=to_ticks(sec=7), enabled=False
        always_use=True, pstate_check=pstate_ultimate, negative_pstate_check=True),
    
    Action("Fury", max=157, cooldown=to_ticks(sec=5)),
    
    Action("Sever", max=188, cooldown=to_ticks(sec=15)),
    
    Action("Slice", min=30, max=120, cooldown=to_ticks(sec=3)),
    
    Action("Smash", max=125, cooldown=to_ticks(sec=10)),
    
    Action("Hurricane", min=(66+84), max=(219+161), cooldown=to_ticks(sec=20),
        adrenaline_change= -15, pstate_check=pstate_threshold_melee),
        
    Action("Bersker", max=0, cooldown=to_ticks(sec=60), adrenaline_change= -100,
        pstate_check=pstate_ultimate, mod=berserk_mod, modable=False),
        
    Action("Dismember", max=188, cooldown=to_ticks(sec=6), modable=False),
    
    Action("Assault", max=219, cooldown=to_ticks(sec=30), number_of_hits=4,
        adrenaline_change= -15, ticks=6, pstate_check=pstate_threshold_melee),
        
    Action("Quake", max=219, cooldown=to_ticks(20), mod=quake_modifier,
        adrenaline_change= -15, pstate_check=pstate_threshold_melee),
        
    Action("Slaughter(Still)", min=100, max=250, cooldown=to_ticks(sec=30),
        adrenaline_change= -15, pstate_check=pstate_threshold_melee,
        buddy_actions=["Slaughter(Move)"], modable=False),
        
    Action("Slaughter(Move)", min=100*3, max=250*3, cooldown=to_ticks(sec=30),
        adrenaline_change= -15, pstate_check=pstate_threshold_melee,
        buddy_actions=["Slaughter(Still)"], modable=False, enabled=False),
]


class ActionLoader(object):
    def __init__(self, action_file):
        with open(action_file, "r") as f:
            self.action_data = ast.literal_eval(f.read())
        
    def get_actions(self, styles=None, filter=None):
        actions = []
                
        # Iterate over all of our action data
        for k in self.action_data.keys():
            # Check if the key is in our keys
            if styles is None or k in styles:                
                # Iterate over our actions to check our filter
                for action in self.action_data[k]:
                    filter_check = True
                
                    # If we have a filter, need to check it over
                    if filter is not None:
                        for k in filter.keys():
                            if k in action and action.get(k, None) != filter[k]:
                                filter_check = False
                                break # Filter failed - moving to next action
                    
                    if filter_check is False:
                        continue
                    
                    # Convert our cooldown into ticks
                    if action.get("cooldown", None) is not None:
                        action["cooldown"] = to_ticks(sec=action.get("cooldown"))
                    
                    # Append the action to our list since it passed the filters
                    actions.append(Action(**action))
    
        return actions

##############################################################
        
TEST_MODE = False
        
def test():
    
    al = ActionLoader("abilities.json")
    
    actions = al.get_actions(filter={"equipment":"2H"})
    
    for a in actions:
        print("{0} | Cooldown: {1}".format(a, a.cooldown))

##############################################################
        
    
def main():
    if TEST_MODE:
        test()
        return
    
    pstate = PState(melee_2h_actions, adrenaline=0, use_ringofvigour=True, use_prng=False)
    total_ticks = to_ticks(sec=60)
    
    rotation = greedy_value(pstate, total_ticks)
    current_tick = 1
    
    for a in rotation:
        print("{0:3} [{1:3}%] | {4:3.2f}% dpt | {2} ({3}) {5}".format(
            current_tick, a["adrenaline"], getattr(a["action"], "name", "SKIP"),
            getattr(a["action"], "ticks", 1), a["value"], a["mods"]
        ))
        current_tick += getattr(a["action"], "ticks", 1)
        
    total_value = get_total(rotation)
    most_used,uses = pstate.get_most_used()
    most_value,value = pstate.get_most_value()
        
    print()
    print("Damage Summary:")
    print("| Execution Ticks: {0}".format(total_ticks))
    print("| Rotation Total:  {0:.2f}% ability dmg".format(total_value))
    print("| Average Action:  {0:.2f}% dpt".format(total_value / total_ticks))
    print()
    print("Frequency & Value:")
    print("| Most used action:  {0} ({1}x)".format(most_used.name, uses))
    print("| Most value action: {0} (~{1:.2f}% of total)".format(most_value.name, (value / total_value) * 100))

    print()
    
    print("Adrenaline Info:")
    print("| Total adrenaline gained:  {0}".format(pstate.gained_adrenaline))
    print("| Total adrenaline spent:   {0}".format(pstate.spent_adrenaline))
    print("| Excess adrenaline wasted: {0}".format(pstate.excess_adrenaline))
    print("| Dmg per spent adrenaline: {0}".format(sum([a.total_used_value for a in pstate.actions if a.adrenaline_change < 0]) / pstate.spent_adrenaline))
    
    print()
    
    print("Usage by action ({0} actions):".format(len([a for a in rotation if a["action"] is not None])))
    for a in sorted(pstate.actions, key=lambda a: a.times_used, reverse=True):
        print("| {0:25} ({1}x)".format(a.name, a.times_used))
    
if __name__ == "__main__":
    main()   
    
