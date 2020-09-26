from collections import OrderedDict, namedtuple
import copy
import hashlib
import io
import itertools
import logging
import os, os.path
import platform
import random
import shutil
import subprocess
import sys
import struct
import time
import zipfile

from Region import get_region_area_name
from Location import Location
from World import World
from Spoiler import Spoiler
from Rom import Rom
from Patches import patch_rom
from Cosmetics import patch_cosmetics
from DungeonList import create_dungeons
from Fill import distribute_items_restrictive, ShuffleError
from Item import Item
from ItemPool import generate_itempool
from Hints import buildGossipHints, get_hint_area
from Utils import default_output_path, is_bundled, subprocess_args, data_path
from version import __version__
from N64Patch import create_patch_file, apply_patch_file
from SettingsList import setting_infos, logic_tricks
from Rules import set_rules, set_shop_rules
from Plandomizer import Distribution
from Search import Search, RewindableSearch, AreaFirstSearch
from EntranceShuffle import set_entrances
from LocationList import set_drop_location_names


class dummy_window():
    def __init__(self):
        pass
    def update_status(self, text):
        pass
    def update_progress(self, val):
        pass


def main(settings, window=dummy_window()):

    start = time.process_time()

    logger = logging.getLogger('')

    old_tricks = settings.allowed_tricks
    settings.load_distribution()

    # compare pointers to lists rather than contents, so even if the two are identical
    # we'll still log the error and note the dist file overrides completely.
    if old_tricks and old_tricks is not settings.allowed_tricks:
        logger.error('Tricks are set in two places! Using only the tricks from the distribution file.')

    for trick in logic_tricks.values():
        settings.__dict__[trick['name']] = trick['name'] in settings.allowed_tricks

    # we load the rom before creating the seed so that errors get caught early
    if settings.compress_rom == 'None' and not settings.create_spoiler:
        raise Exception('`No Output` must have spoiler enabled to produce anything.')

    if settings.compress_rom != 'None':
        window.update_status('Loading ROM')
        rom = Rom(settings.rom)
    else:
        rom = None

    if not settings.world_count:
        settings.world_count = 1
    elif settings.world_count < 1 or settings.world_count > 255:
        raise Exception('World Count must be between 1 and 255')

    # Bounds-check the player_num settings, in case something's gone wrong we want to know.
    if settings.player_num < 1:
        raise Exception(f'Invalid player num: {settings.player_num}; must be between (1, {settings.world_count})')
    if settings.player_num > settings.world_count:
        if settings.compress_rom not in ['None', 'Patch']:
            raise Exception(f'Player Num is {settings.player_num}; must be between (1, {settings.world_count})')
        settings.player_num = settings.world_count

    logger.info('OoT Randomizer Version %s  -  Seed: %s', __version__, settings.seed)
    settings.remove_disabled()
    logger.info('(Original) Settings string: %s\n', settings.settings_string)
    random.seed(settings.numeric_seed)
    settings.resolve_random_settings(cosmetic=False)
    logger.debug(settings.get_settings_display())
    max_attempts = 10
    for attempt in range(1, max_attempts + 1):
        try:
            spoiler = generate(settings, window)
            break
        except ShuffleError as e:
            logger.warning('Failed attempt %d of %d: %s', attempt, max_attempts, e)
            if attempt >= max_attempts:
                raise
            else:
                logger.info('Retrying...\n\n')
            settings.reset_distribution()
    return patch_and_output(settings, window, spoiler, rom, start)


def generate(settings, window):
    logger = logging.getLogger('')
    worlds = []
    for i in range(0, settings.world_count):
        worlds.append(World(i, settings))

    window.update_status('Creating the Worlds')
    for id, world in enumerate(worlds):
        logger.info('Generating World %d.' % (id + 1))

        window.update_progress(0 + 1*(id + 1)/settings.world_count)
        logger.info('Creating Overworld')

        if settings.logic_rules == 'glitched':
            overworld_data = os.path.join(data_path('Glitched World'), 'Overworld.json')
        else:
            overworld_data = os.path.join(data_path('World'), 'Overworld.json')

        # Compile the json rules based on settings
        world.load_regions_from_json(overworld_data)
        create_dungeons(world)
        world.create_internal_locations()

        if settings.shopsanity != 'off':
            world.random_shop_prices()
        world.set_scrub_prices()

        window.update_progress(0 + 4*(id + 1)/settings.world_count)
        logger.info('Calculating Access Rules.')
        set_rules(world)

        window.update_progress(0 + 5*(id + 1)/settings.world_count)
        logger.info('Generating Item Pool.')
        generate_itempool(world)
        set_shop_rules(world)
        set_drop_location_names(world)
        world.fill_bosses()

    if settings.triforce_hunt:
        settings.distribution.configure_triforce_hunt(worlds)

    logger.info('Setting Entrances.')
    set_entrances(worlds)

    window.update_status('Placing the Items')
    logger.info('Fill the world.')
    distribute_items_restrictive(window, worlds)
    window.update_progress(35)

    spoiler = Spoiler(worlds)
    if settings.create_spoiler:
        window.update_status('Calculating Spoiler Data')
        logger.info('Calculating playthrough.')
        create_playthrough(spoiler)
        window.update_progress(50)
    if settings.create_spoiler or settings.hints != 'none':
        window.update_status('Calculating Hint Data')
        logger.info('Calculating hint data.')
        update_required_items(spoiler)
        buildGossipHints(spoiler, worlds)
        window.update_progress(55)
    spoiler.build_file_hash()
    return spoiler


def patch_and_output(settings, window, spoiler, rom, start):
    logger = logging.getLogger('')
    logger.info('Patching ROM.')
    worlds = spoiler.worlds
    cosmetics_log = None

    settings_string_hash = hashlib.sha1(settings.settings_string.encode('utf-8')).hexdigest().upper()[:5]
    if settings.output_file:
        outfilebase = settings.output_file
    elif settings.world_count > 1:
        outfilebase = 'OoT_%s_%s_W%d' % (settings_string_hash, settings.seed, settings.world_count)
    else:
        outfilebase = 'OoT_%s_%s' % (settings_string_hash, settings.seed)

    output_dir = default_output_path(settings.output_dir)

    if settings.compress_rom == 'Patch':
        rng_state = random.getstate()
        file_list = []
        window.update_progress(65)
        for world in worlds:
            if settings.world_count > 1:
                window.update_status('Patching ROM: Player %d' % (world.id + 1))
                patchfilename = '%sP%d.zpf' % (outfilebase, world.id + 1)
            else:
                window.update_status('Patching ROM')
                patchfilename = '%s.zpf' % outfilebase

            random.setstate(rng_state)
            patch_rom(spoiler, world, rom)
            cosmetics_log = patch_cosmetics(settings, rom)
            rom.update_header()

            window.update_progress(65 + 20*(world.id + 1)/settings.world_count)

            window.update_status('Creating Patch File')
            output_path = os.path.join(output_dir, patchfilename)
            file_list.append(patchfilename)
            create_patch_file(rom, output_path)
            rom.restore()
            window.update_progress(65 + 30*(world.id + 1)/settings.world_count)

            if settings.create_cosmetics_log and cosmetics_log:
                window.update_status('Creating Cosmetics Log')
                if settings.world_count > 1:
                    cosmetics_log_filename = "%sP%d_Cosmetics.txt" % (outfilebase, world.id + 1)
                else:
                    cosmetics_log_filename = '%s_Cosmetics.txt' % outfilebase
                cosmetics_log.to_file(os.path.join(output_dir, cosmetics_log_filename))
                file_list.append(cosmetics_log_filename)
            cosmetics_log = None

        if settings.world_count > 1:
            window.update_status('Creating Patch Archive')
            output_path = os.path.join(output_dir, '%s.zpfz' % outfilebase)
            with zipfile.ZipFile(output_path, mode="w") as patch_archive:
                for file in file_list:
                    file_path = os.path.join(output_dir, file)
                    patch_archive.write(file_path, file.replace(outfilebase, ''), compress_type=zipfile.ZIP_DEFLATED)
            for file in file_list:
                os.remove(os.path.join(output_dir, file))
        logger.info("Created patchfile at: %s" % output_path)
        window.update_progress(95)

    elif settings.compress_rom != 'None':
        window.update_status('Patching ROM')
        patch_rom(spoiler, worlds[settings.player_num - 1], rom)
        cosmetics_log = patch_cosmetics(settings, rom)
        window.update_progress(65)

        window.update_status('Saving Uncompressed ROM')
        if settings.world_count > 1:
            filename = "%sP%d.z64" % (outfilebase, settings.player_num)
        else:
            filename = '%s.z64' % outfilebase
        output_path = os.path.join(output_dir, filename)
        rom.write_to_file(output_path)
        if settings.compress_rom == 'True':
            window.update_status('Compressing ROM')
            logger.info('Compressing ROM.')

            if is_bundled():
                compressor_path = "."
            else:
                compressor_path = "Compress"

            if platform.system() == 'Windows':
                if 8 * struct.calcsize("P") == 64:
                    compressor_path += "\\Compress.exe"
                else:
                    compressor_path += "\\Compress32.exe"
            elif platform.system() == 'Linux':
                if platform.uname()[4] == 'aarch64' or platform.uname()[4] == 'arm64':
                    compressor_path += "/Compress_ARM64"
                else:
                    compressor_path += "/Compress"
            elif platform.system() == 'Darwin':
                compressor_path += "/Compress.out"
            else:
                compressor_path = ""
                logger.info('OS not supported for compression')

            output_compress_path = output_path[:output_path.rfind('.')] + '-comp.z64'
            if compressor_path != "":
                run_process(window, logger, [compressor_path, output_path, output_compress_path])
            os.remove(output_path)
            logger.info("Created compressed rom at: %s" % output_compress_path)
        else:
            logger.info("Created uncompressed rom at: %s" % output_path)
        window.update_progress(95)

    if not settings.create_spoiler or settings.output_settings:
        settings.distribution.update_spoiler(spoiler, False)
        window.update_status('Creating Settings Log')
        settings_path = os.path.join(output_dir, '%s_Settings.json' % outfilebase)
        settings.distribution.to_file(settings_path, False)
        logger.info("Created settings log at: %s" % ('%s_Settings.json' % outfilebase))
    if settings.create_spoiler:
        settings.distribution.update_spoiler(spoiler, True)
        window.update_status('Creating Spoiler Log')
        spoiler_path = os.path.join(output_dir, '%s_Spoiler.json' % outfilebase)
        settings.distribution.to_file(spoiler_path, True)
        logger.info("Created spoiler log at: %s" % ('%s_Spoiler.json' % outfilebase))

    if settings.create_cosmetics_log and cosmetics_log:
        window.update_status('Creating Cosmetics Log')
        if settings.world_count > 1 and not settings.output_file:
            filename = "%sP%d_Cosmetics.txt" % (outfilebase, settings.player_num)
        else:
            filename = '%s_Cosmetics.txt' % outfilebase
        cosmetic_path = os.path.join(output_dir, filename)
        cosmetics_log.to_file(cosmetic_path)
        logger.info("Created cosmetic log at: %s" % cosmetic_path)

    if settings.enable_distribution_file:
        window.update_status('Copying Distribution File')
        try:
            filename = os.path.join(output_dir, '%s_Distribution.json' % outfilebase)
            shutil.copyfile(settings.distribution_file, filename)
            logger.info("Copied distribution file to: %s" % filename)
        except:
            logger.info('Distribution file copy failed.')

    window.update_progress(100)
    if cosmetics_log and cosmetics_log.error:
        window.update_status('Success: Rom patched successfully. Some cosmetics could not be applied.')
    else:
        window.update_status('Success: Rom patched successfully')
    logger.info('Done. Enjoy.')
    logger.debug('Total Time: %s', time.process_time() - start)

    return worlds[settings.player_num - 1]


def from_patch_file(settings, window=dummy_window()):
    start = time.process_time()
    logger = logging.getLogger('')

    # we load the rom before creating the seed so that error get caught early
    if settings.compress_rom == 'None' or settings.compress_rom == 'Patch':
        raise Exception('Output Type must be a ROM when patching from a patch file.')
    window.update_status('Loading ROM')
    rom = Rom(settings.rom)

    logger.info('Patching ROM.')

    filename_split = os.path.basename(settings.patch_file).split('.')

    if settings.output_file:
        outfilebase = settings.output_file
    else:
        outfilebase = filename_split[0]

    extension = filename_split[-1]

    output_dir = default_output_path(settings.output_dir)
    output_path = os.path.join(output_dir, outfilebase)

    window.update_status('Patching ROM')
    if extension == 'zpf':
        subfile = None
    else:
        subfile = 'P%d.zpf' % (settings.player_num)
        if not settings.output_file:
            output_path += 'P%d' % (settings.player_num)
    apply_patch_file(rom, settings.patch_file, subfile)
    cosmetics_log = None
    if settings.repatch_cosmetics:
        cosmetics_log = patch_cosmetics(settings, rom)
    window.update_progress(65)

    window.update_status('Saving Uncompressed ROM')
    uncompressed_output_path = output_path + '.z64'
    rom.write_to_file(uncompressed_output_path)
    if settings.compress_rom == 'True':
        window.update_status('Compressing ROM')
        logger.info('Compressing ROM.')

        if is_bundled():
            compressor_path = "."
        else:
            compressor_path = "Compress"

        if platform.system() == 'Windows':
            if 8 * struct.calcsize("P") == 64:
                compressor_path += "\\Compress.exe"
            else:
                compressor_path += "\\Compress32.exe"
        elif platform.system() == 'Linux':
            compressor_path += "/Compress"
        elif platform.system() == 'Darwin':
            compressor_path += "/Compress.out"
        else:
            compressor_path = ""
            logger.info('OS not supported for compression')

        output_compress_path = output_path + '-comp.z64'
        if compressor_path != "":
            run_process(window, logger, [compressor_path, uncompressed_output_path, output_compress_path])
        os.remove(uncompressed_output_path)
        logger.info("Created compressed rom at: %s" % output_compress_path)
    else:
        logger.info("Created uncompressed rom at: %s" % output_path)

    window.update_progress(95)

    if settings.create_cosmetics_log and cosmetics_log:
        window.update_status('Creating Cosmetics Log')
        if settings.world_count > 1 and not settings.output_file:
            filename = "%sP%d_Cosmetics.txt" % (outfilebase, settings.player_num)
        else:
            filename = '%s_Cosmetics.txt' % outfilebase
        cosmetic_path = os.path.join(output_dir, filename)
        cosmetics_log.to_file(cosmetic_path)
        logger.info("Created cosmetic log at: %s" % cosmetic_path)

    window.update_progress(100)
    if cosmetics_log and cosmetics_log.error:
        window.update_status('Success: Rom patched successfully. Some cosmetics could not be applied.')
    else:
        window.update_status('Success: Rom patched successfully')

    logger.info('Done. Enjoy.')
    logger.debug('Total Time: %s', time.process_time() - start)

    return True


def cosmetic_patch(settings, window=dummy_window()):
    start = time.process_time()
    logger = logging.getLogger('')

    if settings.patch_file == '':
        raise Exception('Cosmetic Only must have a patch file supplied.')

    window.update_status('Loading ROM')
    rom = Rom(settings.rom)

    logger.info('Patching ROM.')

    filename_split = os.path.basename(settings.patch_file).split('.')

    if settings.output_file:
        outfilebase = settings.output_file
    else:
        outfilebase = filename_split[0]

    extension = filename_split[-1]

    output_dir = default_output_path(settings.output_dir)
    output_path = os.path.join(output_dir, outfilebase)

    window.update_status('Patching ROM')
    if extension == 'zpf':
        subfile = None
    else:
        subfile = 'P%d.zpf' % (settings.player_num)
    apply_patch_file(rom, settings.patch_file, subfile)
    window.update_progress(65)

    # clear changes from the base patch file
    patched_base_rom = copy.copy(rom.buffer)
    rom.changed_address = {}
    rom.changed_dma = {}
    rom.force_patch = []

    window.update_status('Patching ROM')
    patchfilename = '%s_Cosmetic.zpf' % output_path
    cosmetics_log = patch_cosmetics(settings, rom)
    window.update_progress(80)

    window.update_status('Creating Patch File')

    # base the new patch file on the base patch file
    rom.original.buffer = patched_base_rom
    rom.update_header()
    create_patch_file(rom, patchfilename)
    logger.info("Created patchfile at: %s" % patchfilename)
    window.update_progress(95)

    if settings.create_cosmetics_log and cosmetics_log:
        window.update_status('Creating Cosmetics Log')
        if settings.world_count > 1 and not settings.output_file:
            filename = "%sP%d_Cosmetics.txt" % (outfilebase, settings.player_num)
        else:
            filename = '%s_Cosmetics.txt' % outfilebase
        cosmetic_path = os.path.join(output_dir, filename)
        cosmetics_log.to_file(cosmetic_path)
        logger.info("Created cosmetic log at: %s" % cosmetic_path)

    window.update_progress(100)
    if cosmetics_log and cosmetics_log.error:
        window.update_status('Success: Rom patched successfully. Some cosmetics could not be applied.')
    else:
        window.update_status('Success: Rom patched successfully')

    logger.info('Done. Enjoy.')
    logger.debug('Total Time: %s', time.process_time() - start)

    return True


def run_process(window, logger, args):
    process = subprocess.Popen(args, **subprocess_args(True))
    filecount = None
    while True:
        line = process.stdout.readline()
        if line != b'':
            find_index = line.find(b'files remaining')
            if find_index > -1:
                files = int(line[:find_index].strip())
                if filecount == None:
                    filecount = files
                window.update_progress(65 + 30*(1 - files/filecount))
            logger.info(line.decode('utf-8').strip('\n'))
        else:
            break


def copy_worlds(worlds):
    worlds = [world.copy() for world in worlds]
    Item.fix_worlds_after_copy(worlds)
    return worlds


def update_required_items(spoiler):
    worlds = spoiler.worlds

    # get list of all of the progressive items that can appear in hints
    # all_locations: all progressive items. have to collect from these
    # item_locations: only the ones that should appear as "required"/WotH
    all_locations = [location for world in worlds for location in world.get_filled_locations()]
    # Set to test inclusion against
    item_locations = {location for location in all_locations if location.item.majoritem and not location.locked and location.item.name != 'Triforce Piece'}

    # if the playthrough was generated, filter the list of locations to the
    # locations in the playthrough. The required locations is a subset of these
    # locations. Can't use the locations directly since they are location to the
    # copied spoiler world, so must compare via name and world id
    if spoiler.playthrough:
        translate = lambda loc: worlds[loc.world.id].get_location(loc.name)
        spoiler_locations = set(map(translate, itertools.chain.from_iterable(spoiler.playthrough.values())))
        item_locations &= spoiler_locations

    required_locations = []

    search = Search([world.state for world in worlds])
    for location in search.iter_reachable_locations(all_locations):
        # Try to remove items one at a time and see if the game is still beatable
        if location in item_locations:
            old_item = location.item
            location.item = None
            # copies state! This is very important as we're in the middle of a search
            # already, but beneficially, has search it can start from
            if not search.can_beat_game():
                required_locations.append(location)
            location.item = old_item
        search.state_list[location.item.world.id].collect(location.item)

    # Filter the required location to only include location in the world
    required_locations_dict = {}
    for world in worlds:
        required_locations_dict[world.id] = list(filter(lambda location: location.world.id == world.id, required_locations))
    spoiler.required_locations = required_locations_dict


def locations_to_area_map(locations):
    area_map = {}
    for location in locations:
        area = get_region_area_name(location.parent_region)
        if area not in area_map:
            area_map[area] = {location}
        else:
            area_map[area].add(location)
    return area_map


Sphere = namedtuple('Sphere', ['area_map', 'age_list'])


def create_playthrough(spoiler):
    worlds = spoiler.worlds
    if worlds[0].check_beatable_only and not Search([world.state for world in worlds]).can_beat_game():
        raise RuntimeError('Uncopied is broken too.')
    # create a copy as we will modify it
    old_worlds = worlds
    worlds = copy_worlds(worlds)

    # if we only check for beatable, we can do this sanity check first before writing down spheres
    if worlds[0].check_beatable_only and not Search([world.state for world in worlds]).can_beat_game():
        raise RuntimeError('Cannot beat game. Something went terribly wrong here!')

    search = RewindableSearch([world.state for world in worlds])
    # Get all item locations in the worlds
    item_locations = search.progression_locations()
    # Omit certain items from the playthrough
    internal_locations = {location for location in item_locations if location.internal}
    # Generate a list of spheres by iterating over reachable locations without collecting as we go.
    # Collecting every item in one sphere means that every item
    # in the next sphere is collectable. Will contain every reachable item this way.
    logger = logging.getLogger('')
    logger.debug('Building up collection spheres.')
    collection_spheres = []
    entrance_spheres = []
    remaining_entrances = set(entrance for world in worlds for entrance in world.get_shuffled_entrances())

    while True:
        search.checkpoint()
        # Not collecting while the generator runs means we only get one sphere at a time
        # Otherwise, an item we collect could influence later item collection in the same sphere
        collected = list(search.iter_reachable_locations(item_locations))
        if not collected: break
        # Gather the new entrances before collecting items.
        collection_spheres.append(collected)
        accessed_entrances = set(filter(search.spot_access, remaining_entrances))
        entrance_spheres.append(accessed_entrances)
        remaining_entrances -= accessed_entrances
        for location in collected:
            # Collect the item for the state world it is for
            search.collect(location.item)
    logger.info('Collected %d spheres', len(collection_spheres))

    # Reduce each sphere in reverse order, by checking if the game is beatable
    # when we remove the item. We do this to make sure that progressive items
    # like bow and slingshot appear as early as possible rather than as late as possible.
    required_locations = []
    for sphere in reversed(collection_spheres):
        for location in sphere:
            # we remove the item at location and check if the game is still beatable in case the item could be required
            old_item = location.item

            # Uncollect the item and location.
            search.uncollect(old_item)
            search.unvisit(location)

            # Generic events might show up or not, as usual, but since we don't
            # show them in the final output, might as well skip over them. We'll
            # still need them in the final pass, so make sure to include them.
            if location.internal:
                required_locations.append(location)
                continue

            location.item = None

            # An item can only be required if it isn't already obtained or if it's progressive
            if search.state_list[old_item.world.id].item_count(old_item.name) < old_item.world.max_progressions[old_item.name]:
                # Test whether the game is still beatable from here.
                logger.debug('Checking if %s is required to beat the game.', old_item.name)
                if not search.can_beat_game():
                    # still required, so reset the item
                    location.item = old_item
                    required_locations.append(location)

    # Reduce each entrance sphere in reverse order, by checking if the game is beatable when we disconnect the entrance.
    required_entrances = []
    for sphere in reversed(entrance_spheres):
        for entrance in sphere:
            # we disconnect the entrance and check if the game is still beatable
            old_connected_region = entrance.disconnect()

            # we use a new search to ensure the disconnected entrance is no longer used
            sub_search = Search([world.state for world in worlds])

            # Test whether the game is still beatable from here.
            logger.debug('Checking if reaching %s, through %s, is required to beat the game.', old_connected_region.name, entrance.name)
            if not sub_search.can_beat_game():
                # still required, so reconnect the entrance
                entrance.connect(old_connected_region)
                required_entrances.append(entrance)

    # Regenerate the spheres as we might not reach places the same way anymore.
    search.reset() # search state has no items, okay to reuse sphere 0 cache
    collection_spheres = []
    entrance_spheres = []
    remaining_entrances = set(required_entrances)
    collected = set()
    while True:
        # Not collecting while the generator runs means we only get one sphere at a time
        # Otherwise, an item we collect could influence later item collection in the same sphere
        collected.update(search.iter_reachable_locations(required_locations))
        if not collected: break
        internal = collected & internal_locations
        if internal:
            # collect only the internal events but don't record them in a sphere
            for location in internal:
                search.collect(location.item)
            # Remaining locations need to be saved to be collected later
            collected -= internal
            continue
        # Gather the new entrances before collecting items.
        collection_spheres.append(list(collected))
        accessed_entrances = set(filter(search.spot_access, remaining_entrances))
        entrance_spheres.append(accessed_entrances)
        remaining_entrances -= accessed_entrances
        for location in collected:
            # Collect the item for the state world it is for
            search.collect(location.item)
        collected.clear()
    logger.info('Collected %d final spheres', len(collection_spheres))

    # Then we can finally output our playthrough
    spoiler.playthrough = OrderedDict((str(i + 1), {location: location.item for location in sphere}) for i, sphere in enumerate(collection_spheres))

    if worlds[0].entrance_shuffle != 'off':
        spoiler.entrance_playthrough = OrderedDict((str(i + 1), list(sphere)) for i, sphere in enumerate(entrance_spheres))


    # Area Sphere playthrough:
    # summary:
    # 0) produce regular playthrough
    # 1) determine required areas from playthrough locations
    # 2) collect playthrough locations separately by area, in spheres
    # 3) attempt to merge areas into later spheres, validate each merge
    # 4) re-collect area-spheres into spheres for final output

    # alternate approach idea:
    # 0) regular playthrough
    # 1) determine required locations (aka woth), turn into required areas
    # 2) sum playthrough items
    # 3) find items in required areas where possible; where not possible, add new areas to required

    # 0) skip regular playthrough
    # 1) determine required locations (aka woth), turn into required areas
    #    this will not include replaceables
    # 2) ?? find necessary items somehow?
    #    or use as input to an area+age-based search:

    # different search to build initial area+age-based playthrough:
    # - store per-world: current age, visited/unvisited but reached areas
    # - expand regions: don't consider entrances in unvisited areas
    # - iterate: collect locations in current age in visited areas
    #   when none are left, consider unvisited areas (in some order? all at once?)
    #    by marking them visited, and inc sphere count.
    #   when no unvisited areas, and Time Travel, switch age, inc sphere, mark starting area visited

    class InvalidPlaythrough(Exception):
        pass

    # Called after merging two areas together. Tests whether the merge was
    # valid and attempts to move spheres to satisfy this
    # input: current search, list of Spheres, area being tested, low/high sphere idx
    # modifies area_spheres
    # returns new search or throws exception
    def validate_spheres(search, area_spheres, test_area, low, high):
        sub_search = search.copy()
        low = sub_search.rewind(low)
        exceptions = []

        # recalculate sphere search over sphere range
        for s in range(low, high+1):
            sphere_locations = set()
            # collect each area
            for area, locations in area_spheres[s].area_map.items():
                sub_search.collect_locations(locations, internal_locations)

                # Test if area is still reachable
                if not all(map(sub_search.visited, locations)):
                    # Playthrough spheres are not valid
                    if area == test_area:
                        # If the merged area is unreachable so this merge is invalid
                        logger.debug(f'{area} of sphere {s+1} is not reachable and cannot be moved.')

                        raise InvalidPlaythrough(f'{area} of sphere {s+1} is not reachable and cannot be moved.')
                    # Otherwise attempt to move the unreachable area to later
                    exceptions.append((s, area))
                else:
                    sphere_locations |= locations
                sub_search.rewind()

            # Collect the sphere items
            sub_search.collect_locations(sphere_locations, internal_locations)
            sub_search.checkpoint()

        # Attempt to move any unreachable areas
        for (s, area) in exceptions:
            # Move the sphere into a new sphere level
            high += 1
            locations = area_spheres[s].area_map[area]

            # Test if the move solved the reachability
            sphere_locations = set()
            sub_search.collect_locations(locations, internal_locations)
            for location in locations:
                if not sub_search.visited(location):
                    # The area is still unreachable so this merge is invalid
                    logger.debug(f'{location.name} in sphere {s+1} is not reachable.')
                    raise InvalidPlaythrough(f'{location.name} in sphere {s+1} is not reachable.')
            # Move successful
            area_spheres.insert(high, Sphere({area: locations}, sub_search.current_ages()))
            del area_spheres[s].area_map[area]
            sub_search.checkpoint()

        # Merge was successful, return the new search
        return sub_search


    # Try to merge the area with the next occurence of the area in the spheres
    # input: search, list of Spheres, idx of sphere with area, area in that sphere
    # returns: search, Sphere list after attempt at merging.
    # TODO: attempt to merge only within each world? Does that make sense? It otherwise seems silly
    # to attempt merging areas from different worlds.
    def merge_areas(search, area_spheres, low, area):
        assert area in area_spheres[low].area_map
        for high in range(low+1, len(area_spheres)):
            if area in area_spheres[high].area_map:
                # Found a match, attempt to merge them
                try:
                    # Create a sphere set with the areas merged
                    new_spheres = [
                            Sphere(
                                {a: set(locations) for a, locations in sphere.area_map.items()},
                                sphere.age_list)
                        for sphere in area_spheres]
                    new_spheres[high].area_map[area] |= new_spheres[low].area_map[area]
                    del new_spheres[low].area_map[area]

                    # Test if the merge is valid
                    new_search = validate_spheres(search, new_spheres, area, low, high)

                    # Return new search/spheres if merge is valid
                    return new_search, new_spheres
                except InvalidPlaythrough as e:
                    # Merge is not valid so make no changes
                    return search, area_spheres

        # No duplicate found, make no changes
        return search, area_spheres


    # input: search, Sphere list, required_entrances
    # returns: search, Sphere list, [{entrance} sets]
    def reduce_area_spheres(search, sphere_list, required_entrances):
        # Merge all possible areas in the spheres
        s = 0
        while s < len(sphere_list):
            sphere = sphere_list[s]
            for area in sphere.area_map:
                if area not in sphere_list[s].area_map:
                    search, sphere_list = merge_areas(search, sphere_list, s, area)
            s += 1

        # Rebuild spheres: Some of the added spheres can likely be merged with later spheres
        # Calculate entrance playthrough
        entrance_spheres = []
        remaining_entrances = set(required_entrances)
        # list of Sphere
        final_area_spheres = []
        # list of (area, locations) tuples across all spheres
        area_spheres = [(area, locations) for sphere_ in sphere_list for area, locations in sphere_.area_map.items()]
        search.reset()
        # area map for one sphere
        sphere_area_map = {}
        collected_locations = set()

        # Collect each area individually
        for area, locations in area_spheres:
            search.collect_locations(locations, internal_locations)
            if not all(map(search.visited, locations)):
                # If the area is not reachable, then it must be in the next sphere
                search.rewind()

                # Calculate reachable entrances
                accessed_entrances = set(filter(search.spot_access, remaining_entrances))
                entrance_spheres.append(accessed_entrances)
                remaining_entrances -= accessed_entrances

                # Collect the sphere items
                search.collect_locations(collected_locations, internal_locations)
                search.checkpoint()
                final_area_spheres.append(Sphere(sphere_area_map, search.current_ages()))

                # Start the next sphere
                collected_locations = set()
                sphere_area_map = {}

            # Add the area to the sphere
            sphere_area_map[area] = locations
            collected_locations |= locations
            search.rewind()

        # Add the final sphere
        final_area_spheres.append(sphere)
        accessed_entrances = set(filter(search.spot_access, remaining_entrances))
        entrance_spheres.append(accessed_entrances)
        remaining_entrances -= accessed_entrances
        return search, final_area_spheres, entrance_spheres

    # New area search
    worlds = copy_worlds(old_worlds)
    area_search = AreaFirstSearch([world.state for world in worlds])
    # Get all item locations in the worlds
    item_locations = area_search.progression_locations()
    # Omit certain items from the playthrough
    internal_locations = {location for location in item_locations if location.internal}
    key_locations = set(filter(Location.has_area_item, item_locations))
    auto_locations = internal_locations | key_locations
    area_collection_spheres = []
    entrance_spheres = []
    remaining_entrances = set(entrance for world in worlds for entrance in world.get_shuffled_entrances())

    while True:
        area_search.checkpoint()
        # Not collecting while the generator runs means we only get one sphere at a time
        # Otherwise, an item we collect could influence later item collection in the same sphere
        collected = list(area_search.iter_reachable_locations(item_locations, auto_locations))
        if not collected:
            collected.extend(area_search.iter_reachable_locations(item_locations, auto_locations))
            if not collected:
                break
        # Gather the new entrances before collecting items.
        area_collection_spheres.append(collected)
        accessed_entrances = set(filter(area_search.spot_access, remaining_entrances))
        entrance_spheres.append(accessed_entrances)
        remaining_entrances -= accessed_entrances
        for location in collected:
            if location not in auto_locations:
                # Collect the item for the state world it is for
                area_search.collect(location.item)
    logger.info('Collected %d area-based spheres', len(area_collection_spheres))

    # Reduce each sphere in reverse order, by checking if the game is beatable
    # when we remove the item. We do this to make sure that progressive items
    # like bow and slingshot appear as early as possible rather than as late as possible.
    required_locations = []
    for sphere in reversed(area_collection_spheres):
        # Drop everything in the sphere first; auto locations may affect others.
        area_search.rewind()
        for location in sphere:
            # we remove the item at location and check if the game is still beatable in case the item could be required
            old_item = location.item

            # Generic events might show up or not, as usual, but since we don't
            # show them in the final output, might as well skip over them.
            # We'll still include them in the final sphere generation.
            if location.internal:
                continue

            location.item = None

            # An item can only be required if it isn't already obtained or if it's progressive
            if area_search.state_list[old_item.world.id].item_count(old_item.name) < old_item.world.max_progressions[old_item.name]:
                # Test whether the game is still beatable from here.
                fail = not area_search.can_beat_game()
                logger.debug(f'I have {area_search.state_list[old_item.world.id].item_count(old_item.name)} of {old_item.name}; another {"*is*" if fail else "is *not*"} required to beat the game.')
                if fail:
                    # still required, so reset the item
                    location.item = old_item
                    required_locations.append(location)

    # Reduce each entrance sphere in reverse order, by checking if the game is beatable when we disconnect the entrance.
    required_entrances = []
    for sphere in reversed(entrance_spheres):
        for entrance in sphere:
            # we disconnect the entrance and check if the game is still beatable
            old_connected_region = entrance.disconnect()

            # we use a new search to ensure the disconnected entrance is no longer used
            sub_search = Search([world.state for world in worlds])

            # Test whether the game is still beatable from here.
            logger.debug('Checking if reaching %s, through %s, is required to beat the game.', old_connected_region.name, entrance.name)
            if not sub_search.can_beat_game():
                # still required, so reconnect the entrance
                entrance.connect(old_connected_region)
                required_entrances.append(entrance)

    # Regenerate the spheres as we might not reach places the same way anymore.
    # New search, since deleting entrances may have isolated areas
    area_search = AreaFirstSearch([world.state for world in worlds])
    sphere_list = []
    entrance_spheres = []
    remaining_entrances = set(required_entrances)
    collected = []
    # Reduce the list of keys and such
    key_locations = set(filter(Location.has_area_item, required_locations))
    auto_locations = internal_locations | key_locations
    retries = 0
    while not area_search.can_beat_game(False):
        area_search.checkpoint()
        # Not collecting while the generator runs means we only get one sphere at a time
        # Otherwise, an item we collect could influence later item collection in the same sphere
        # However, we allow some locations to be collected automatically to accomplish exactly that.
        collected.extend(area_search.iter_reachable_locations(required_locations, auto_locations))
        if not collected:
            if retries > 1:
                raise InvalidPlaythrough(f'Failed to collect required items or win playthrough after {retries} consecutive searches.')
            retries += 1
            continue
        retries = 0
        # Gather the new entrances before collecting items.
        sphere_list.append(Sphere(locations_to_area_map(collected), area_search.current_ages()))
        # Might not be accurate; entrances can be used despite not looting a new area
        accessed_entrances = set(filter(area_search.spot_access, remaining_entrances))
        entrance_spheres.append(accessed_entrances)
        remaining_entrances -= accessed_entrances
        for location in collected:
            if location not in auto_locations:
                # Collect the item for the state world it is for
                area_search.collect(location.item)
        collected.clear()
    logger.info('Reduced to %d area-based spheres', len(sphere_list))

    final_area_spheres = sphere_list
    #area_search, final_area_spheres, _ = reduce_area_spheres(area_search, sphere_list, required_entrances)
    #logger.info('Merged into %d final area spheres', len(final_area_spheres))

    # Generate playthrough spoiler structs
    spoiler.area_playthrough = OrderedDict((i, {f'World {k + 1} ({age})': {} for k, age in enumerate(sphere.age_list)}) for i, sphere in enumerate(final_area_spheres))
    for i, sphere in enumerate(final_area_spheres):
        for area, locations in sphere.area_map.items():
            for location in locations:
                w = f'World {location.world.id + 1} ({sphere.age_list[location.world.id]})'
                if area not in spoiler.area_playthrough[i][w]:
                    spoiler.area_playthrough[i][w][area] = [location]
                else:
                    spoiler.area_playthrough[i][w][area].append(location)
        for w in list(spoiler.area_playthrough[i].keys()):
            if not spoiler.area_playthrough[i][w]:
                del spoiler.area_playthrough[i][w]

    if worlds[0].entrance_shuffle != 'off':
        spoiler.entrance_playthrough = OrderedDict((str(i + 1), list(sphere)) for i, sphere in enumerate(entrance_spheres))
