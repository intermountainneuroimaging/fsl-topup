"""Main module."""

import logging
import os
import errorhandler
from typing import List, Tuple
import json
import nibabel as nb
from fw_gear_fsl_topup import mri_qa
import shutil

from utils.command_line import exec_command, build_command_list
from fw_gear_fsl_topup.common import execute_shell, searchfiles

log = logging.getLogger(__name__)

# Track if message gets logged with severity of error or greater
error_handler = errorhandler.ErrorHandler()

##--------    Gear Specific files/folders   --------##
DEFAULT_CONFIG = '/flywheel/v0/b02b0.cnf'


def prepare(
        options: dict,
) -> Tuple[List[str], List[str]]:
    """Prepare everything for the algorithm run.

    It should:
     - Install FreeSurfer license (if needed)

    Same for FW and RL instances.
    Potentially, this could be BIDS-App independent?

    Args:
        options (Dict): gear options

    Returns:
        errors (list[str]): list of generated errors
        warnings (list[str]): list of generated warnings
    """
    # pylint: disable=unused-argument
    # for now, no errors or warnings, but leave this in place to allow future methods
    # to return an error
    errors: List[str] = []
    warnings: List[str] = []

    return errors, warnings
    # pylint: enable=unused-argument


def run(options, gear_context):

    # Check the inputs and categorize files
    log.info('Locating opposing phase encoded fieldmap images')
    pairs = locate_fieldmap_pairs(options["fmaps"])

    for imgs in pairs:
        corrected_files = []

        log.info("Using fieldmaps: %s", ", ".join(imgs))

        # Run Topup on the inputs
        log.info('Running Topup')

        topup_dir = os.path.join(options["work-dir"],"topup")
        os.makedirs(topup_dir, exist_ok=True)

        options["Image1"] = imgs[0]
        options["Image2"] = imgs[1]

        topup_input = generate_topup_input(options)

        acq_input = generate_acquisition_params(options)

        topup_out = run_topup(options, topup_input, acq_input, topup_dir)

        log.info('Checking intended-fors')

        apply_to_files, acq_param_idxs = locate_apply_to_files(options)

        # Try to apply topup to input files
        log.info('Applying Topup Correction')
        corrected_files.extend(apply_topup(apply_to_files, acq_param_idxs, topup_out, acq_input))

        if error_handler.fired:
            log.critical('Failure: exiting with code 1 due to logged errors')
            run_error = 1
            return run_error

        # move output files to path with destination-id
        for f in corrected_files:
            newpath = f.replace(str(options["work-dir"]), os.path.join(options["work-dir"],options["destination-id"]))
            os.makedirs(os.path.dirname(newpath), exist_ok=True)
            shutil.copy(f, newpath, follow_symlinks=True)

        # Try to run topup QA
        # apply_to_files is currently a list of [(filename, index), ... ].  We need to combine this
        # with corrected files so that we have [(original file, corrected file), ... ]
        file_comparison = [(apply_to_files[i], corrected_files[i]) for i in range(len(corrected_files))]
        work_dir = options["work-dir"]
        output_dir = options["output-dir"]
        try:
            if gear_context.config['QA']:
                log.info('Running Topup QA')
                for original, corrected in file_comparison:
                    report_out = mri_qa.generate_topup_report(original, corrected, work_dir)
                    report_dir, report_base = os.path.split(report_out)
                    shutil.move(report_out, os.path.join(output_dir, report_base))

                    # Move the config file used in the analysis to the output
                    config_path = gear_context.get_input_path('config_file')

                    # If this wasn't provided as input, save to output for provenance.
                    if not config_path:
                        config_path = DEFAULT_CONFIG
                        config_out = os.path.join(output_dir, 'config_file.txt')
                        if os.path.exists(config_path):
                            shutil.copy(config_path, config_out)
                        else:
                            log.info(f'no path {config_path}')

        except Exception as e:
            raise Exception("Error running topup QC") from e

    # zip results
    cmd = "zip -q -r " + os.path.join(options["output-dir"],
                                      "topup_" + str(options["destination-id"])) + ".zip " + options[
              "destination-id"]
    execute_shell(cmd, dryrun=options["dry-run"], cwd=options["work-dir"])

def locate_fieldmap_pairs(fmaps):
    # first remove the "dir" component - then look for label duplicates
    fmaps_stripped = ["_".join([x for x in s.split("_") if "dir" not in x]) for s in fmaps]

    # custom function
    def itemgetter(a, b): return [a[i] for i in b]

    pairs=[]
    for tmpl in sorted(set(fmaps_stripped)):
        if fmaps_stripped.count(tmpl) == 2:
            # this is a good match - return the full name
            idxs = [i for i, x in enumerate(fmaps_stripped) if x == tmpl]
            match = itemgetter(fmaps,idxs)
            pairs.append(match)

    return pairs


def locate_apply_to_files(options):
    # check for supplied intended for json first...
    if "intended_for" in options:
        intended_for_file = options["intended_for"]
    else:
        intended_for_file = options["Image1"].replace("nii.gz", "json")

    filelist = find_metadata(intended_for_file, "IntendedFor")

    outfiles = []
    parentdir = os.path.join(options["inputs-dir"],"sub-"+options["sid"])
    for path in filelist:
        # look for the file first...
        f = searchfiles(os.path.join(parentdir, path), exit_on_errors=False)
        if f:
            outfiles.extend(f)

    if outfiles:
        dir1 = [s for s in options["Image1"].split("_") if "dir" in s][0]
        dir2 = [s for s in options["Image2"].split("_") if "dir" in s][0]

        # return a final list of files to apply topup and acquisition parameter index
        apply_to_files, acq_param_idxs = assign_acqparam_index(outfiles, dir1, dir2)
        return apply_to_files, acq_param_idxs

    else:
        log.error("No files found to apply topup.")


def assign_acqparam_index(files, dir1, dir2):
    outindices = []
    outfiles = []
    for f in files:
        if dir1 in f.lower():
            outindices.append("1")
            outfiles.append(f)
        elif dir2 in f.lower():
            outindices.append("2")
            outfiles.append(f)
        else:
            log.warning("unable to apply topup to file %s.", f)

    return outfiles, outindices

def find_metadata(file, parameter):
    with open(file) as f:
        data = json.load(f)
        value = data[parameter]
    return value


def generate_acquisition_params(options):
    if "acq_par" in options:
        return options["acq_par"]

    # build acquisition parameters based on fieldmap files
    image1 = options["Image1"]
    image2 = options["Image2"]

    readout1 = find_metadata(image1.replace("nii.gz","json"), 'TotalReadoutTime')
    readout2 = find_metadata(image2.replace("nii.gz", "json"), 'TotalReadoutTime')

    lines = []
    if "dir-ap" in str(image1).lower():
        lines.append("0 -1 0 "+str(readout1))
    elif "dir-pa" in str(image1).lower():
        lines.append("0 1 0 "+str(readout1))

    if "dir-ap" in str(image2).lower():
        lines.append("0 -1 0 "+str(readout2))
    elif "dir-pa" in str(image2).lower():
        lines.append("0 1 0 "+str(readout2))

    with open(os.path.join(options["work-dir"],"topup","acq_params.txt"), 'w') as f:
        f.write('\n'.join(lines))

    return os.path.join(options["work-dir"],"topup","acq_params.txt")


def is4D(image):
    """Checks to see if a given image is 4D

    Args:
        image (str): path to image

    Returns:
        (bool): true if image is 4d, false otherwise.

    """
    shape = nb.load(image).header.get_data_shape()
    if len(shape) < 4:
        return (False)
    elif shape[3] > 1:
        return (True)
    else:
        return (False)


def check_inputs(context):
    """Check gear inputs

    Checks the inputs of the gear and determines TOPUP run settings, and generates a list of files to apply TOPUP to
    (if indicated by the user)

    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context

    Returns:
        apply_to_files (list): a list of files to apply the TOPUP correction to after calculating the TOPUP fieldmaps
        index_list (list): the row index in the acquisition_parameters file associated with each file in apply_to_files
    """

    apply_to_files = []

    # Capture all the inputs from the gear context
    image1_path = context.get_input_path('_image_1')
    image2_path = context.get_input_path('_image_2')
    config_path = context.get_input_path('_config_file')
    apply_to_a = context.get_input_path('_apply_to_1')
    apply_to_b = context.get_input_path('_apply_to_2')
    acq_par = context.get_input_path('_acquisition_parameters')

    # If image_1 is 4D, we will apply topup correction to the entire series after running topup
    if is4D(image1_path):
        apply_to_files.append((image1_path,
                               '1'))  # '1' Referring to the row this image is associated with in the "acquisition_parameters" file
        log.info('Will run applytopup on {}'.format(image1_path))

    # If image_2 is 4D, we will apply topup correction to the entire series after running topup
    if is4D(image2_path):
        apply_to_files.append((image2_path, '2'))
        log.info('Will run applytopup on {}'.format(image2_path))

    # If apply_to_a is provided, applytopup to this image, too.
    # NOTE that apply_to_a must correspond to row 1 in the acquisition_parameters file
    if apply_to_a:
        apply_to_files.append((apply_to_a, '1'))
        log.info('Will run applytopup on {}'.format(apply_to_a))

    # If apply_to_b is provided, applytopup to this image, too.
    # NOTE that apply_to_b must correspond to row 2 in the acquisition_parameters file
    if apply_to_b:
        apply_to_files.append((apply_to_b, '2'))
        log.info('Will run applytopup on {}'.format(apply_to_b))

    # Read in the parameters and print them to the log
    parameters = open(acq_par, 'r')
    log.info(parameters.read())
    parameters.close()

    if config_path:
        log.info('Using config settings in {}'.format(config_path))
    else:
        log.info('Using default config values')

    return (apply_to_files)


def generate_topup_input(options):
    """Takes gear input files and generates a merged input file for TOPUP.

    Args:
        options (dict): containing relevant settings and options for gear

    Returns:
        merged (string): the path to the merged file for use in TOPUP

    """

    # Capture the paths of the input files from the gear context
    image1_path = options["Image1"]
    image2_path = options["Image2"]
    work_dir = options["work-dir"]

    # Create a base directory in the context's working directory for image 1
    base_out1 = os.path.join(work_dir, 'topup', 'Image1')

    # If image 1 is 4D, we will only use the first volume (Assuming that a 4D image is fMRI and we only need one volume)
    # TODO: Allow the user to choose which volume to use for topup correction
    if is4D(image1_path):
        im_name = os.path.split(image1_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        # Generate a command to extract the first volume
        cmd = ['fslroi', image1_path, base_out1, '0', '1']
    else:
        # If the image is 3D, simply copy the image to our working directory using fslmaths because it's extension agnostic
        cmd = ['fslmaths', image1_path, base_out1]

    # Execute the command, resulting in a single volume from image_1 in the working directory
    exec_command(cmd)

    # Repeat the same steps with image 2
    base_out2 = os.path.join(work_dir, 'topup', 'Image2')
    if is4D(image2_path):
        im_name = os.path.split(image2_path)[-1]
        log.info('Using volume 1 in 4D image {}'.format(im_name))

        cmd = ['fslroi', image2_path, base_out2, '0', '1']
    else:
        cmd = ['fslmaths', image2_path, base_out2]
    exec_command(cmd)

    # Merge the two volumes (image_1 then image_2)
    merged = os.path.join(work_dir, 'topup', 'topup_vols')
    cmd = ['fslmerge', '-t', merged, base_out1, base_out2]
    exec_command(cmd)

    return (merged)


def run_topup(options, input, acq_params, topup_dir):
    """Runs topup on a given input image.

    Requires acquisition parameters and input options from the gear context.

    Args:
        options (dict): flywheel gear context
        input (string): the path to the input file for topup's 'imain' input option
        acq_params (string): the path to the acquisition parameters file matching the input image order
        topup_dir (string): path to location to store results

    Returns:
        out (string): the topup root path

    """

    # Get the output directory and config file from the gear context
    output_dir = topup_dir
    acq_par = acq_params

    # If the user didn't provide a config file, use the default
    if "config_path" not in options:
        config_path = DEFAULT_CONFIG
    else:
        config_path = options["config_path"]

    # Setup output directories
    fout = os.path.join(output_dir, 'topup-fmap')
    iout = os.path.join(output_dir, 'topup-input-corrected')
    out = os.path.join(output_dir, 'topup')
    logout = os.path.join(output_dir, 'topup-log.txt')

    # Get output options from the gear context (which commands to include in the topup call)
    dfout = options['displacement_field']
    jacout = options['jacobian_determinants']
    rbmout = options['rigid_body_matrix']
    verbose = options['verbose']
    debug = options['topup_debug_level']
    # lout = context.config['mystery_output']

    # Begin generating the command arguments with the default commands that are always present
    argument_dict = {'imain': input, 'datain': acq_par, 'out': out, 'fout': fout,
                     'iout': iout, 'logout': logout, 'config': config_path}

    # Add the optional commands defined by the user in the config settings
    if dfout:
        argument_dict['dfout'] = out + '-dfield'
    if jacout:
        argument_dict['jacout'] = out + '-jacdet'
    if rbmout:
        argument_dict['rbmout'] = out + '-rbmat'
    if verbose:
        argument_dict['verbose'] = True
    if debug:
        argument_dict['debug'] = debug

    # Print the config file settings to the log
    log.info('Using config settings:\n\n{}\n\n'.format(open(config_path, 'r').read()))

    # Build the command and execute
    command = build_command_list(['topup'], argument_dict)
    exec_command(command)

    return (out)


def apply_topup(apply_topup_files, index_list, topup_out, acq_params):
    """Applies a calculated topup correction to a list of files.

    Args:
        context (class: `flywheel.gear_context.GearContext`): flywheel gear context
        apply_topup_files (list): A list of files to apply topup correction to
        index_list (list): A list that corresponds 1:1 with apply_topup_files, this indicates which row to use from the
        "acquisition_parameters" text file for the associated file.  This essentially tells topup what PE direction each
        image is.
        topup_out (string): the base directory/filename for the topup analysis that was run previously.

    Returns:
        output_files (list): a list of topup corrected files

    """

    output_files = []

    # For all the files we're applying topup to, loop through them with their associated row in the acquisition parameter file
    for ix, fl in enumerate(apply_topup_files):
        # Generate an output name: "topup_corrected_" appended to the front of the original filename
        base = os.path.split(fl)[-1]
        output_file = os.path.join(os.path.dirname(fl), 'topup-corrected-{}'.format(base))
        output_files.append(output_file)

        # Generate the applytopup command
        cmd = ['applytopup',
               '--imain={}'.format(fl),
               '--datain={}'.format(acq_params),
               '--inindex={}'.format(index_list[ix]),
               '--topup={}'.format(topup_out),
               '--method=jac',
               '--interp=spline',
               '--out={}'.format(output_file)]

        # Execute the command
        exec_command(cmd)

    return (output_files)


