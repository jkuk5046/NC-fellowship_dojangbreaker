import time
import numpy as np
import sc2
import sc2.position as position

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.buff_id import BuffId
from collections import OrderedDict


class Bot(sc2.BotAI):
    def __init__(self, *args, **kwargs):
        super().__init__()
        unitTable = [UnitTypeId.MARINE, UnitTypeId.MARAUDER, UnitTypeId.REAPER, UnitTypeId.GHOST, UnitTypeId.HELLION,
                     UnitTypeId.SIEGETANK, UnitTypeId.SIEGETANKSIEGED, UnitTypeId.THOR, UnitTypeId.MEDIVAC, UnitTypeId.VIKINGFIGHTER,
                     UnitTypeId.VIKINGASSAULT, UnitTypeId.BANSHEE, UnitTypeId.RAVEN, UnitTypeId.BATTLECRUISER, UnitTypeId.AUTOTURRET, UnitTypeId.MULE, UnitTypeId.COMMANDCENTER]
        self.unitSupply = {UnitTypeId.MARINE : 1, UnitTypeId.MARAUDER : 2, UnitTypeId.REAPER : 1, UnitTypeId.GHOST : 2,
                      UnitTypeId.HELLION : 2, UnitTypeId.SIEGETANK : 3, UnitTypeId.SIEGETANKSIEGED : 3, UnitTypeId.THOR : 6,
                      UnitTypeId.MEDIVAC : 2, UnitTypeId.VIKINGFIGHTER : 2, UnitTypeId.VIKINGASSAULT : 2, UnitTypeId.BANSHEE : 6,
                      UnitTypeId.RAVEN : 2, UnitTypeId.BATTLECRUISER : 6, UnitTypeId.AUTOTURRET : 0, UnitTypeId.MULE : 0, UnitTypeId.COMMANDCENTER : 0}

        self.priority  = dict() # attack priority table
        for attacker in unitTable:
            for target in unitTable:
                self.priority[(attacker, target)] = 0
        self.priority[(UnitTypeId.MARAUDER, UnitTypeId.MARAUDER)] = 1
        self.priority[(UnitTypeId.MARAUDER, UnitTypeId.SIEGETANK)] = 6
        self.priority[(UnitTypeId.MARAUDER, UnitTypeId.SIEGETANKSIEGED)] = 6

        self.march_sen = False  # flag indicating whether to go attack or not


    def on_start(self):
        self.target_unit_counts = {
            UnitTypeId.COMMANDCENTER: 0,
            UnitTypeId.MARINE: 6,
            UnitTypeId.MARAUDER: 2,
            UnitTypeId.MEDIVAC: 1,
            #UnitTypeId.SIEGETANK: 1,
        }
        self.evoked = dict()

    def default_action(self, actions, unit, target, rally): # decides the action : march and attack / retreat and rally
        if self.march_sen:
            actions.append(unit.attack(target))
        elif self.known_enemy_units.exists:
            if rally.distance_to(self.known_enemy_units.closest_to(rally)) < 20:
                actions.append(unit.attack(target))
            else:
                actions.append(unit.move(rally))
        else:
            actions.append(unit.move(rally))


    async def on_step(self, iteration: int):
        actions = list()

        ccs = self.units(UnitTypeId.COMMANDCENTER).idle
        combat_supply = 0
        for unit in self.units:
            if unit.type_id is UnitTypeId.MEDIVAC:
                continue
            combat_supply += self.unitSupply[unit.type_id]
        combat_units = self.units.exclude_type([UnitTypeId.COMMANDCENTER, UnitTypeId.MEDIVAC])
        my_supply = self.supply_army
        enemy_supply = 0
        for unit in self.known_enemy_units:
            enemy_supply += self.unitSupply[unit.type_id]
        wounded_units = self.units.filter(lambda u: u.is_biological and u.health_percentage < 1.0)
        enemy_cc = self.enemy_start_locations[0]

        if my_supply >= 30:
            self.march_sen = True
        elif enemy_supply - combat_supply > 5 or combat_supply <= 10:
            self.march_sen = False

        unit_counts = dict()
        for unit in self.units:
            unit_counts[unit.type_id] = unit_counts.get(unit.type_id, 0) + 1

        target_unit_counts = np.array(list(self.target_unit_counts.values()))
        target_unit_ratio = target_unit_counts / (target_unit_counts.sum() + 1e-6)
        current_unit_counts = np.array([unit_counts.get(tid, 0) for tid in self.target_unit_counts.keys()])
        current_unit_ratio = current_unit_counts / (current_unit_counts.sum() + 1e-6)
        unit_ratio = (target_unit_ratio - current_unit_ratio).clip(0, 1)


        if ccs.exists:
            cc = ccs.first
            next_unit = list(self.target_unit_counts.keys())[unit_ratio.argmax()]
            if self.can_afford(next_unit) and self.time - self.evoked.get((cc.tag, 'train'), 0) > 1.0:
                actions.append(cc.train(next_unit))
                self.evoked[(cc.tag, 'train')] = self.time

        ######################################################### Unit Micro

        radius = 25.0   # concave radius
        length = len(combat_units)  # length of the concave(arc)
        concave_angle = length / radius # angle of the targeted arc
        theta = np.pi-(concave_angle/2) # angle for a single unit (increases by d_theta for each units)
        d_theta = concave_angle
        if length != 0:
            d_theta /= length
        rally_point_center = self.start_location + 0.5 * (enemy_cc - self.start_location) # center of the concave circle
        current_units_unsorted = OrderedDict()  # keeps track of current units

        for unit in self.units.not_structure:
            current_units_unsorted[unit.tag] = unit
        current_units = sorted(current_units_unsorted.items())

        for temp in current_units: # IMPORTANT! instead of iterating self.units.not_structure, iterate in current_units to iterate through the units in the same order
            unit = temp[1] #current_units is a list of tuples(key, value)
            target = enemy_cc
            targetWeight = -100
            if unit.type_id is not UnitTypeId.MEDIVAC:
                if self.known_enemy_units.exists:
                    for enemy_unit in self.known_enemy_units: # search for the enemy with the highest weight, considering the distance from this unit
                        if self.priority[(unit.type_id, enemy_unit.type_id)] - unit.distance_to(enemy_unit) > targetWeight:
                            target = enemy_unit
                            targetWeight = self.priority[(unit.type_id, enemy_unit.type_id)] - unit.distance_to(enemy_unit)


            if unit.type_id is UnitTypeId.MARINE:
                rally_point = rally_point_center + position.Point2(
                    position.Pointlike((radius * np.cos(np.array([theta]))[0], radius * np.sin(np.array([theta]))[0]))
                )   # calculates the position of this unit in concave
                theta += d_theta    #calculates the theta for the next unit
                self.default_action(actions, unit, target, rally_point) #decides this units action

                if unit.distance_to(target) < 15 and self.march_sen:
                    if not unit.has_buff(BuffId.STIMPACK) and unit.health_percentage > 0.5:
                        if self.time - self.evoked.get((unit.tag, AbilityId.EFFECT_STIM), 0) > 1.0:
                            actions.append(unit(AbilityId.EFFECT_STIM))
                            self.evoked[(unit.tag, AbilityId.EFFECT_STIM)] = self.time

            if unit.type_id is UnitTypeId.MARAUDER:
                rally_point = rally_point_center + position.Point2(
                    position.Pointlike((radius * np.cos(np.array([theta]))[0], radius * np.sin(np.array([theta]))[0]))
                )
                theta += d_theta
                self.default_action(actions, unit, target, rally_point)

                if unit.distance_to(target) < 15 and self.march_sen:
                    if not unit.has_buff(BuffId.STIMPACKMARAUDER) and unit.health_percentage > 0.5:
                        if self.time - self.evoked.get((unit.tag, AbilityId.EFFECT_STIM_MARAUDER), 0) > 1.0:
                            actions.append(unit(AbilityId.EFFECT_STIM_MARAUDER))
                            self.evoked[(unit.tag, AbilityId.EFFECT_STIM_MARAUDER)] = self.time

            if unit.type_id is UnitTypeId.SIEGETANK:
                rally_point = rally_point_center + position.Point2(
                    position.Pointlike((radius * np.cos(np.array([theta]))[0], radius * np.sin(np.array([theta]))[0]))
                )
                theta += d_theta
                self.default_action(actions, unit, target, rally_point)

                if unit.distance_to(target) <= 13 and self.march_sen:
                    if self.time - self.evoked.get((unit.tag, AbilityId.SIEGEMODE_SIEGEMODE), 0) > 0.5:
                        actions.append(unit(AbilityId.SIEGEMODE_SIEGEMODE))
                        self.evoked[(unit.tag, AbilityId.SIEGEMODE_SIEGEMODE)] = self.time

            if unit.type_id is UnitTypeId.SIEGETANKSIEGED:
                if not self.known_enemy_units.exists:
                    if self.time - self.evoked.get((unit.tag, AbilityId.UNSIEGE_UNSIEGE), 0) > 0.5:
                        actions.append(unit(AbilityId.UNSIEGE_UNSIEGE))
                        self.evoked[(unit.tag, AbilityId.UNSIEGE_UNSIEGE)] = self.time


            if unit.type_id is UnitTypeId.MEDIVAC:
                if wounded_units.exists:
                    wounded_unit = wounded_units.closest_to(unit)
                    actions.append(unit(AbilityId.MEDIVACHEAL_HEAL, wounded_unit))
                elif combat_units.exists:
                    actions.append(unit.move(combat_units.center))
                else:
                    actions.append(unit.move(rally_point_center + position.Point2(-25, 0)))

        await self.do_actions(actions)

