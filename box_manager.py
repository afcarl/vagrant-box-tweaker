#!/usr/bin/env python

################################################################################
# Copyright (c) 2015 Genome Research Ltd.
#
# Author: Matthew Rahtz <matthew.rahtz@sanger.ac.uk>
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be included
# in all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
# CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
# TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
################################################################################

"""
'create' verb: create a Vagrant box using a specified provisioning file and
               create a Vagrant Cloud JSON file describing the box version,
               suitable for use with 'vagrant add'. If the JSON file already
               exists, update it for the new version.

'prune': verb: clear out old versions of boxes
"""

from __future__ import print_function
import json
import hashlib
import argparse
import subprocess
import os.path
import os
import shutil
import stat
import grp

INSTALL_DIR = "/opt/vagrant_boxes"
# where the 'boxes' directory is actually served to the outside world
# (e.g. file://..., http://...)
VAGRANT_BOXES_PUBLIC_URL = "http://vagrant.foocorp.com"
LOCAL_BUILD_DIR = "/tmp"

BOXES_DIR = os.path.join(INSTALL_DIR, 'boxes')
BUILD_TEMPLATES_DIR = os.path.join(INSTALL_DIR, 'build_templates')

def process_args():
    """
    Set up argument parser, and call appropriate function depending on what verb
    is selected
    """

    main_description = ("Create and manage customised versions of standard "
                        "Vagrant boxes.")
    parser = argparse.ArgumentParser(
        description=main_description,
    )

    subparsers = parser.add_subparsers()
    create_description = ("Create a Vagrant box from an existing standard box "
                          "with the specified provisioning script applied. "
                          "Also create/update a JSON file describing the box "
                          "version, suitable for use with 'vagrant add'.")
    
    parser_create = subparsers.add_parser('create',
            description=create_description,
            help='Create/update a box')
    prune_description = "Prune all but the latest n versions of a box."
    parser_prune = subparsers.add_parser('prune',
            description=prune_description,
            help='Prune old versions of a box')

    parser_create.add_argument('source_box',
        help='Source box on which to base new box (e.g. ubuntu/precise64)')
    parser_create.add_argument('provision_script',
        help=('Name of provisioning script that will be applied to the '
               'source box in order to create the new box (should exist in '
               'build_templates/)'))
    parser_create.add_argument('target_box',
        help='Name of box that will be created (e.g. foocorp/precise64)')
    parser_create.add_argument('box_id',
        help='Unique identifier for the created box')
    parser_create.set_defaults(func=create_box)

    parser_prune.add_argument('box',
        help='Name of box to prune (e.g. foocorp/precise64)')
    parser_prune.add_argument('n',
        type=int,
        help='Number of most recent versions to keep')
    parser_prune.set_defaults(func=prune_boxes)

    args_list = parser.parse_args()

    # call the function corresponding to the verb specified
    args_list.func(args_list)

def create_box(args):
    """
    Orchestrate the process of creating a new version of a box
    """
    build_directory = set_up_build_directory(BUILD_TEMPLATES_DIR, args.box_id)

    provision_script_path = \
        os.path.join(BUILD_TEMPLATES_DIR, args.provision_script)
    if not os.path.isfile(provision_script_path):
        msg = "Error: provisioning script '%s' does not exist in '%s'" % \
            (args.provision_script, BUILD_TEMPLATES_DIR)
        raise Exception(msg)

    try:
        box_output_filename = build_box(
            build_directory,
            args.source_box,
            args.provision_script
        )
    except subprocess.CalledProcessError as err:
        clean_up_build_dir(build_directory)
        raise err

    box_description = \
        "Generated from source box '%s' using provisioning script '%s'" \
            % (args.source_box, args.provision_script)
    update_box_list(
        box_output_filename,
        box_description,
        args.target_box,
        args.box_id
    )
    clean_up_build_dir(build_directory)

def escape_box_name(box_name):
    """
    Remove special characters from box name
    """
    return box_name.replace('/', '_')

def get_box_dir_name(box_name):
    """
    Get the name of the directory relative to the boxes dir where the .box
    files are stored
    """
    return escape_box_name(box_name)

def get_box_dir_path(box_name):
    """
    Return the full path on the filesystem to the directory where the .box files
    are stored
    """
    boxes_dir = os.path.join(INSTALL_DIR, 'boxes')
    return os.path.join(boxes_dir, get_box_dir_name(box_name))

def get_box_json_path(box_name):
    """
    Get the full path on the filesystem of the .json file describing the box
    versions
    """
    return get_box_dir_path(box_name) + '.json'

def prune_boxes(args):
    """
    Remove all but the newest N versions of a given box
    """

    box_dir = get_box_dir_path(args.box)
    box_json_filename = get_box_json_path(args.box)

    if not os.path.exists(box_json_filename):
        raise Exception("Box JSON file '%s' does not exist" % box_json_filename)

    with open(box_json_filename, 'r') as box_json_file:
        box_file_dict = json.load(box_json_file)

    versions = []
    for version in box_file_dict['versions']:
        version_num = int(version['version'])
        versions.append(int(version['version']))
    # order highest (most recent) versions first
    versions.sort()
    versions.reverse()
    # get the most recent N versions
    keep_versions = versions[0:args.n]

    boxes_to_prune = []
    versions_to_keep = []
    for version in box_file_dict['versions']:
        version_num = int(version['version'])

        if version_num in keep_versions:
            versions_to_keep.append(version)
            continue

        box_url = version['providers'][0]['url']
        box_filename = box_url.split('/')[-1]
        boxes_to_prune.append({
            'version': version_num,
            'filename': os.path.join(box_dir, box_filename)
        })

    box_file_dict['versions'] = versions_to_keep
    with open(box_json_filename, 'w') as box_json_file:
        json.dump(box_file_dict, box_json_file, indent=4)

    for box in boxes_to_prune:
        version = box['version']
        filename = box['filename']
        print("Removing box version %d at %s" % (version, filename))
        os.remove(filename)

def is_world_readable(test_file):
    """
    Check whether the specified file is world-readable
    """
    stat_info = os.stat(test_file)
    return bool(stat_info.st_mode & stat.S_IROTH)

def is_owned_by_group(test_file, expected_group):
    """
    Check whether the specified file is owned by the expected group
    """
    stat_info = os.stat(test_file)
    gid = stat_info.st_gid
    actual_group = grp.getgrgid(gid)[0]
    if actual_group == expected_group:
        return True
    else:
        return False

def set_up_build_directory(build_template_dir, box_id):
    """
    Create a copy of the build template files on a local disk,
    being careful about permissions so that it's not world-readable
    """
    # The box will include a root filesystem, including parts which
    # we don't necessarily want to let other people see (e.g. /etc/shadow),
    # so we're very careful about making sure the temporary build directory
    # is secure
    # shutil.copytree preserves the permissions of the source, so by checking
    # that the source is secure we should be good
    if is_world_readable(build_template_dir):
        msg = "Build template directory '%s' world readable!" \
                % build_template_dir
        raise Exception(msg)

    build_dir = os.path.join(LOCAL_BUILD_DIR, 'vagrant_box_build-' + box_id)
    build_dir = os.path.abspath(build_dir)
    if not build_dir.startswith(LOCAL_BUILD_DIR):
        raise Exception("Build directory '%s' not in '%s'" %
                (build_dir, LOCAL_BUILD_DIR))

    shutil.copytree(build_template_dir, build_dir)

    return build_dir

def clean_up_build_dir(build_dir):
    """
    Remove the temporary build directory, first destroy any VMs
    still existing in it
    """
    print("Cleaning up build directory...")
    env = dict(os.environ)
    env['VAGRANT_CWD'] = build_dir

    subprocess.call(['vagrant', 'destroy', '-f'], env=env)

    shutil.rmtree(build_dir)
    print("done")

def build_box(build_dir, source_box, provision_script):
    """
    Build the Vagrant box from the specified source box using
    the specified provisioning script
    """

    print("Building box using source %s and provisioning script %s..."
        % (source_box, provision_script))

    packaged_box_filename = build_dir + '/package.box'

    env = dict(os.environ)
    env['VAGRANT_CWD'] = build_dir

    print("Creating and provisioning box...")
    # these environment variables are used by the Vagrantfile
    env['SOURCE_BOX'] = source_box
    env['PROVISION_SCRIPT'] = provision_script
    subprocess.check_call(['vagrant', 'up'], env=env)
    print("Provisioning done")

    print("Exporting box...")
    subprocess.check_call(
        ['vagrant', 'package', '--output', packaged_box_filename],
        env=env
    )
    print("Export done")
    print("Box build completed!")
    return packaged_box_filename

def update_box_list(box_file, box_description, target_box, box_id):
    """
    Moves the created box into the right place in INSTALL_DIR
    and updates the JSON version list for that box appropriately
    """

    full_box_path = get_box_dir_path(target_box)
    # prevent directory traversal
    # http://stackoverflow.com/questions/6803505/does-my-code-prevent-directory-traversal
    full_box_path = os.path.abspath(full_box_path)
    if not full_box_path.startswith(BOXES_DIR):
        raise Exception("Box target directory '%s' not in '%s'" %
                (full_box_path, BOXES_DIR))

    if not os.path.exists(full_box_path):
        os.makedirs(full_box_path)

    new_box_filename = box_id + '.box'
    new_box_target = os.path.join(full_box_path, new_box_filename)
    new_box_target = os.path.abspath(new_box_target)
    if not new_box_target.startswith(full_box_path):
        raise Exception("Target box file '%s' not in '%s'" %
                (new_box_target, full_box_path))

    box_json_filename = get_box_json_path(target_box)

    print("Updating box list %s with box ID '%s'" % (box_json_filename, box_id))

    print("Calculating SHA1 checksum...")
    sha1_checksum = sha1_file(box_file)
    print("done")

    print("Copying %s to %s..." % (box_file, new_box_target))
    shutil.copyfile(
        box_file,
        new_box_target
    )
    print("done")

    box_dirname = get_box_dir_name(target_box)
    new_box_url = \
        VAGRANT_BOXES_PUBLIC_URL + "/" + box_dirname + "/" + new_box_filename

    print("Adding box to JSON file...")
    update_box_json(
        box_json_filename,
        target_box,
        box_description,
        new_box_url,
        sha1_checksum
    )
    print("done")

def sha1_file(filename):
    """
    Calculate the SHA1 hash of the given filename,
    reading it in several blocks
    """
    # from http://www.pythoncentral.io/hashing-files-with-python/
    block_size = 65536
    hasher = hashlib.sha1()
    with open(filename, 'rb') as file_to_hash:
        buf = file_to_hash.read(block_size)
        while len(buf) > 0:
            hasher.update(buf)
            buf = file_to_hash.read(block_size)
    return hasher.hexdigest()

def update_box_json(
        box_json_filename, box_name, box_description, box_url, box_sha1):
    """
    Add the specified box file as the latest version to the given
    box JSON file
    """

    if not os.path.isfile(box_json_filename):
        box_file_dict = {
            "description": box_description,
            "name": box_name,
            "versions": []
        }
        new_version_n = 1
    else:
        with open(box_json_filename, 'r') as box_json_file:
            box_file_dict = json.load(box_json_file)
        latest_version_n = 0
        for version in box_file_dict['versions']:
            version_n = int(version['version'])
            if version_n > latest_version_n:
                latest_version_n = version_n
        new_version_n = latest_version_n + 1

    new_version = {
        # Vagrant expects the version number to be quoted
        "version": str(new_version_n),
        "providers": [{
            "name": "virtualbox",
            "url": box_url,
            "checksum_type": "sha1",
            "checksum": box_sha1
        }]
    }

    box_file_dict['versions'].append(new_version)

    with open(box_json_filename, 'w') as box_json_file:
        json.dump(box_file_dict, box_json_file, indent=4)

process_args()
