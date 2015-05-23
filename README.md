## vagrant-box-tweaker

Wrapper for creating and managing customised versions of standard Vagrant box
files. Provides a simple method of creating boxes pre-provisioned with your
standard Puppet or Chef configuration. (See also:
[Veewee](https://github.com/jedi4ever/veewee).)

`build_templates` contains the scripts used to provision the boxes.  The
`Vagrantfile` is a template used for spawning the Vagrant machines used to
generate the boxes.

Each box version for a given target box name will be placed in a
`boxes/<target box name>` folder in the current directory.
A JSON file at `boxes/<target box name>.json` will also be created (and
updated for subsequent builds of the same target box name) which enumerates the versions. The JSON file can then be used with `vagrant box add` to allow Vagrant to check for box update automatically.

Usage:
```
$ ./box_manager.py -h
usage: box_manager.py [-h] {create,prune} ...

Create a Vagrant box and create/update a JSON file describing the box version,
suitable for use with 'vagrant add'.

positional arguments:
  {create,prune}
    create        Create/update a box
    prune         Prune old versions of a box

optional arguments:
  -h, --help      show this help message and exit

$ ./box_manager.py create -h
usage: box_manager.py create [-h]
                             source_box provision_script target_box box_id

positional arguments:
  source_box        Source box on which to base new box (e.g.
                    ubuntu/precise64)
  provision_script  Name of provisioning script that will be applied to the
                    source box in order to create the new box (should exist in
                    build_templates/)
  target_box        Name of box that will be created (e.g. foocorp/precise64)
  box_id            Unique identifier for the created box (e.g. CFEngine Git
                    commit hash)

optional arguments:
  -h, --help        show this help message and exit

$ ./box_manager.py prune -h
usage: box_manager.py prune [-h] box n

positional arguments:
  box         Name of box to prune (e.g. foocorp/precise64)
  n           Number of most recent versions to keep

optional arguments:
  -h, --help  show this help message and exi
```
