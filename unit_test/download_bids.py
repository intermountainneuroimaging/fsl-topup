import os
import os.path as op
from fw_gear_fsl_topup.common import searchfiles
from flywheel_gear_toolkit import GearToolkitContext
os.chdir("/flywheel/v0")
with GearToolkitContext() as gear_context:
    gear_context.client
    gear_context.download_session_bids(
        target_dir=op.join(gear_context.work_dir, "BIDS"),
        folders=['fmap']
    )

    # locate all fieldmap files...
    destination = gear_context.client.get(gear_context.destination["id"])
    sid = gear_context.client.get(destination.parents.subject)
    sesid = gear_context.client.get(destination.parents.session)

    fmapfiles = searchfiles(op.join(gear_context.work_dir, "BIDS","sub-"+sid.label,"ses-"+sesid.label,"fmap/*.nii.gz"))
    print(fmapfiles)