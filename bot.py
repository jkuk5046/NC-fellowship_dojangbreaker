import time
import numpy as np
import sc2

from sc2.ids.ability_id import AbilityId
from sc2.ids.unit_typeid import UnitTypeId
from sc2.ids.buff_id import BuffId


class Bot(sc2.BotAI):
    def __init__(self, *args, **kwargs):
        super().__init__()
        unitTable = [UnitTypeId.MARINE, UnitTypeId.MARAUDER, UnitTypeId.REAPER, UnitTypeId.GHOST, UnitTypeId.HELLION,
                     UnitTypeId.SIEGETANK, UnitTypeId.THOR, UnitTypeId.MEDIVAC, UnitTypeId.VIKING, UnitTypeId.BANSHEE,
                     UnitTypeId.RAVEN, UnitTypeId.BATTLECRUISER, UnitTypeId.AUTOTURRET, UnitTypeId.MULE, UnitTypeId.COMMANDCENTER]
        self.priority  = dict()
        for attacker in unitTable:
            for target in unitTable:
                self.priority[(attacker, target)] = 0
        self.priority[(UnitTypeId.MARAUDER, UnitTypeId.MARAUDER)] = 10
        self.priority[(UnitTypeId.MARAUDER, UnitTypeId.SIEGETANK)] = 20


    def on_start(self):
        self.target_unit_counts = {
            UnitTypeId.COMMANDCENTER: 0,
            UnitTypeId.MARINE: 5,
            UnitTypeId.MARAUDER: 2,
            UnitTypeId.MEDIVAC: 1,
        }
        self.evoked = dict()



    async def on_step(self, iteration: int):
        actions = list()

        ccs = self.units(UnitTypeId.COMMANDCENTER).idle
        wounded_units = self.units.filter(lambda u: u.is_biological and u.health_percentage < 1.0)
        enemy_cc = self.enemy_start_locations[0]

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

        for unit in self.units.not_structure:
            enemy_unit = self.enemy_start_locations[0]
            target = enemy_cc
            targetWeight = -100
            if self.known_enemy_units.exists:
                for enemy_unit in self.known_enemy_units:

                    if self.priority[(unit.type_id, enemy_unit.type_id)] - unit.distance_to(enemy_unit) > targetWeight :
                        target = enemy_unit
                        targetWeight = self.priority[(unit.type_id, enemy_unit.type_id)] - unit.distance_to(enemy_unit)


                #enemy_unit = self.known_enemy_units.closest_to(unit)
                #if unit.distance_to(enemy_cc) > unit.distance_to(enemy_unit):

            if unit.type_id is UnitTypeId.MARINE or unit.type_id is UnitTypeId.MARAUDER:
                actions.append(unit.attack(target))
                if unit.distance_to(target) < 15:
                    if not unit.has_buff(BuffId.STIMPACK) and unit.health_percentage > 0.5:
                        if self.time - self.evoked.get((unit.tag, AbilityId.EFFECT_STIM), 0) > 1.0:
                            actions.append(unit(AbilityId.EFFECT_STIM))
                            self.evoked[(unit.tag, AbilityId.EFFECT_STIM)] = self.time

            if unit.type_id is UnitTypeId.MEDIVAC:
                if wounded_units.exists:
                    wounded_unit = wounded_units.closest_to(unit)
                    actions.append(unit(AbilityId.MEDIVACHEAL_HEAL, wounded_unit))

        await self.do_actions(actions)

