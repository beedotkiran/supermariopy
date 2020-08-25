import warnings
from typing import Iterable

import cv2
import deprecation
import numpy as np
import pandas as pd
from scipy.ndimage.measurements import center_of_mass
from skimage import measure

from . import __version__, metrics
from .pandaslib import df_empty

__all__ = [
    "load_iuv",
    "calculate_centroids",
    "plot_centroids",
    "filter_parts",
    "remap_parts",
    "semantic_remap_dict2remap_dict",
    "compute_iou",
    "resize_labels",
    "compute_best_iou_remapping",
]


def load_iuv(iuv_path):
    """load i,u,v channels from xxx_iuv.png image

    Parameters
    ----------
    iuv_path : [str]

    Returns
    -------
    np.ndarray
        channel of indexes, aka part labels
    np.ndarray
        channel of u coordinates
    np.ndarray
        channel of v coordinates
    """
    iuv = cv2.imread(iuv_path, -1)
    i, u, v = list(map(np.squeeze, np.dsplit(iuv, 3)))
    return i, u, v


def calculate_centroids(labels, cca=False, background=0):
    """
    Calculate centroids from label map.
    Maybe use connected components analysis (cca) before
    to get only connected labels.

    labels : ndarray
        an array of ints giving the corresponding part labels
    cca : bool
        if connected components analysis should be done
        to isolate connected label regions.
    background: int
        which label is considered background and therefore not calculated

    returns
    centroids : list of array
        each array contains ints as centroid locations in pixel coordinates
    centroid_labels : list
        list of int label ids corresponding to centroids

    Examples

    from matplotlib import pylab as plt
    import cv2
    import numpy as np

    image_paths = [
        "front_IUV.png",
        "behind_IUV.png",
    ]

    IUV = list(map( cv2.imread, image_paths))
    I = list(map(lambda x: x[:, :, 0], IUV))

    centroids, centroid_labels = calculate_centroids(I[0], True)
    texts = list(map(str, centroid_labels))
    plt.close("all")
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    ax.imshow(I[0])
    plot_centroids(ax, centroids, texts)
    """
    unique_labels = np.unique(labels)
    unique_labels = set(unique_labels) - set([background])
    label_masks = [labels == label_id for label_id in unique_labels]

    def _calc_centroid(x):
        """ the actual calc centroid function """
        return np.array(center_of_mass(x)).astype(np.int)

    centroids = []
    centroid_labels = []
    for label_mask, label_id in zip(label_masks, unique_labels):
        if cca:
            connected_labels = measure.label(label_mask)
            connected_ids = set(np.unique(connected_labels))
            connected_ids -= set([0])  # suppress background
            connected_masks = [connected_labels == cid for cid in connected_ids]
            current_centroids = list(map(_calc_centroid, connected_masks))
            centroids += current_centroids
            centroid_labels += [label_id] * len(current_centroids)
        else:
            current_centroids = _calc_centroid(label_mask)
            centroids.append(current_centroids)
            centroid_labels.append(label_id)
    return centroids, centroid_labels


def plot_centroids(ax, centroids, texts):
    """
    plot centroid points into image given axis and texts.
    Centroids can be obtained by @calculate_centroids.

    ax : axis handle
        axis handle where to put text
    centroids : list of arrays
        each array contains ints as centroid locations in pixel coordinates
    texts : `list` of `str`
        texts that should be displayed at centroid location

    Examples

    from matplotlib import pylab as plt
    import cv2
    import numpy as np

    image_paths = [
        "front_IUV.png",
        "behind_IUV.png",
    ]

    IUV = list(map( cv2.imread, image_paths))
    I = list(map(lambda x: x[:, :, 0], IUV))

    centroids, centroid_labels = calculate_centroids(I[0], True)
    texts = list(map(str, centroid_labels))
    plt.close("all")
    fig, ax = plt.subplots(1, 1, figsize=(8, 8))
    ax.imshow(I[0])
    plot_centroids(ax, centroids, texts)
    """
    props = dict(boxstyle="round", facecolor="wheat", alpha=0.5)
    for p, t in zip(centroids, texts):
        if np.all(p > 0):
            ax.text(
                p[1], p[0], t, fontsize=10, bbox=props, horizontalalignment="center"
            )


def filter_parts(part_map, included_parts):
    """
    Filter out only included part labels from part_map.

    part_map : np.ndarray
        an array of part labels (int) for each pixel location
    included_parts : list or array
        array of dtype np.int specifying parts that should remain

    returns
    new_part_map : np.ndarray
        an array where only included parts are present.
    """
    new_part_map = np.zeros_like(part_map)
    for i in included_parts:
        mask = part_map == i
        new_part_map[mask] = part_map[mask]
    return new_part_map


def remap_parts(part_map, remap_dict):
    """
    remaps labels according to a remapping dictionary.

    part_map : ndarray
        an array of part labels (int) for each pixel location
    remap_dict : dict
        a dict where each key is an int giving the original part id and
        each value is an int giving the new part id

    returns
    new_part_map : ndarray
        an array with new labels


    Example:

        from matplotlib import pylab as plt
        import cv2
        import numpy as np

        image_paths = [
            "front_IUV.png",
            "behind_IUV.png",
        ]

        IUV = list(map( cv2.imread, image_paths))
        I = list(map(lambda x: x[:, :, 0], IUV))
        I = I[0] # keep it simple
        semantic_remap_dict = {
            "arm" : ['left_upper_arm',
                    'right_upper_arm',
                    'left_upper_arm',
                    'right_upper_arm',
                    'left_lower_arm',
                    'right_lower_arm',
                    'left_lower_arm',
                    'right_lower_arm'
                    ],
            "leg" : [
                'back_upper_front_leg',
                'back_upper_left_leg',
                'right_upper_leg',
                'left_upper_leg',
                'back_right_lower_leg',
                'back_left_lower_leg',
                'right_lower_leg',
                'left_lower_leg'
            ],
            'head': ['left_head', 'right_head'],
            'hand': ['right_hand', 'left_hand'],
            'chest': ['chest'],
            'back' : ['back'],
            'foot': ['left_foot', 'right_foot'],
            'background' : ['background']
        }
        new_part_list = list(semantic_remap_dict.keys())

        remap_dict = {}
        for i, new_label in enumerate(new_part_list):
            old_keys = semantic_remap_dict[new_label]
            remap_dict.update({denseposelib.PART_LIST.index(o) : i for o in old_keys})

        print(remap_dict)

        new_I = denseposelib.remap_parts(I, remap_dict)
        plt.imshow(new_I)
        ax = plt.gca()
        centroids, centroid_labels = denseposelib.calculate_centroids(new_I, cca=True)
        texts = list(map(lambda x: new_part_list[x], centroid_labels))
        denseposelib.plot_centroids(ax, centroids, texts)
    """
    new_part_map = np.zeros_like(part_map)
    for old_id, new_id in remap_dict.items():
        mask = part_map == old_id
        new_part_map[mask] = new_id
    return new_part_map


def semantic_remap_dict2remap_dict(semantic_remap_dict, new_part_list):
    """
    Returns a dictionary of (new_label_id, old_label_id) pairs
    that can be used with @remap_parts to regroup the semantic
    annotation from densepose output.

    semantic_remap_dict: dict
        a dictionary where each key is the new part name (e.g. "arm")
        and each value is a list of old part names
        (e.g. ['left_upper_arm', 'right_upper_arm']).
        The list of old part names have to be from @PART_LIST.
    new_part_list : list
        the complete list of all new part names as `str`

    Example
        semantic_remap_dict = {
            "arm" : ['left_upper_arm',
                    'right_upper_arm',
                    'left_upper_arm',
                    'right_upper_arm',
                    'left_lower_arm',
                    'right_lower_arm',
                    'left_lower_arm',
                    'right_lower_arm'
                    ],
            "leg" : [
                'back_upper_front_leg',
                'back_upper_left_leg',
                'right_upper_leg',
                'left_upper_leg',
                'back_right_lower_leg',
                'back_left_lower_leg',
                'right_lower_leg',
                'left_lower_leg'
            ],
            'head': ['left_head', 'right_head'],
            'hand': ['right_hand', 'left_hand'],
            'chest': ['chest'],
            'back' : ['back'],
            'foot': ['left_foot', 'right_foot'],
            'background' : ['background']
        }
        new_part_list = list(semantic_remap_dict.keys())
        remap_dict = semantic_remap_dict2remap_dict(semantic_remap_dict, new_part_list)

    """
    remap_dict = {}
    for i, new_label in enumerate(new_part_list):
        old_keys = semantic_remap_dict[new_label]
        remap_dict.update({PART_LIST.index(o): i for o in old_keys})
    return remap_dict


def compute_iou(pred, label):
    """
    compoute iou between predicted labels and labels.
    IOU is also called Jaccard Similarity although this is more form the NLP domain.

    pred : ndarray of shape [H, W] and dtype int
        array with predicted labels
    label : ndarray of shape [H, W] and dtype int
        array with ground truth labels

    Returns
    IOU : ndarray of shape [N]
        array with IOUs
    unique_labels : ndarray of shape [n]
        array with unique labels in of GT label array
    """
    unique_labels = np.unique(label)
    num_unique_labels = len(unique_labels)

    Intersection = np.zeros(num_unique_labels)
    Union = np.zeros(num_unique_labels)

    for index, val in enumerate(unique_labels):
        pred_i = pred == val
        label_i = label == val

        Intersection[index] = float(np.sum(np.logical_and(label_i, pred_i)))
        Union[index] = float(np.sum(np.logical_or(label_i, pred_i)))

    return Intersection / Union, unique_labels


@deprecation.deprecated(
    deprecated_in="0.2",
    removed_in="0.3",
    current_version=__version__,
    details="Use the function metrics.compute_best_iou_remapping",
)
def compute_best_iou_remapping(predicted_labels, true_labels):
    return metrics.compute_best_iou_remapping(predicted_labels, true_labels)


def resize_labels(labels, size):
    """Reshape labels image to target size.

    Parameters
    ----------
    labels : np.ndarray
        [H, W] or [N, H, W] - shaped array where each pixel is an `int`
        giving a label id for the segmentation. In case of [N, H, W],
        each slice along the first dimension is treated as an independent label image.
    size : tuple of ints
        Target shape as tuple of ints

    Returns
    -------
    reshaped_labels : np.ndarray
        [size[0], size[1]] or [N, size[0], size[1]]-shaped array

    Raises
    ------
    ValueError
        if labels does not have valid shape
    """
    if len(labels.shape) == 2:
        return cv2.resize(labels, size, interpolation=cv2.INTER_NEAREST)
    elif len(labels.shape) == 3:
        label_list = np.split(labels, labels.shape[0], axis=0)
        label_list = list(
            map(
                lambda x: cv2.resize(
                    np.squeeze(x), size, interpolation=cv2.INTER_NEAREST
                ),
                label_list,
            )
        )
        labels = np.stack(label_list, axis=0)
        return labels
    else:
        raise ValueError("unsupported shape for labels : {}".format(labels.shape))


def calculate_iou_df(
    predicted: np.ndarray, target: np.ndarray, label_names: Iterable[str]
):
    """Calculate IOUs for each (predicted, target) pair in tensor `predicted` and
    `target` and each part in label_names.

    Each IOU measurement is written as a line in a dataframe.

    If a label is not present in `target`, the IOU is set to -1.

    Parameters
    ----------
    inferred : np.ndarray
        A stack of N inferred labels shaped [N, H, W]
    truth : np.ndarray
        A stack of N target labels shaped [N, H, W]
    label_names : list of `str`
        list of semantic names for each label value

    Returns
    -------
    pd.DataFrame
        dataframe with columns [ "batch_idx", label_names[0], ..., label_names[-1] ]

    Examples
    --------

        A = np.ones((10, 10), dtype=np.int)
        B = np.ones((10, 10), dtype=np.int)
        B[:5, :5] = 0
        B[5:, 5:] = 1
        B[5:, :5] = 2

        predicted = np.stack([A] * 10, axis=0)
        target = np.stack([B] * 10, axis=0)
        label_names = ["zeros", "ones", "twos", "threes"]
        df = calculate_iou_df(predicted, target, label_names)
        print(df)
        >>> batch_idx  zeros  ones  twos  threes
        >>>  0.0    0.0   0.5   0.0    -1.0
        >>>  1.0    0.0   0.5   0.0    -1.0
        # ...
    """

    # df = pd.DataFrame(columns=["batch_idx"] + label_names)
    column_names = ["batch_idx"] + label_names
    dtypes = [np.int32] + [np.float32] * len(label_names)
    df = df_empty(column_names, dtypes)
    for batch_idx in range(len(predicted)):
        current_inferred = predicted[batch_idx]
        current_gt = target[batch_idx]
        iou, iou_labels = compute_iou(current_inferred, current_gt)
        df_update = {p: -1.0 for p in label_names}
        df_update.update(
            {
                p: float(np.squeeze(iou[pi == iou_labels]))
                for pi, p in enumerate(label_names)
                if pi in iou_labels
            }
        )
        df_update.update({"batch_idx": batch_idx})
        df = df.append(df_update, ignore_index=True)
    return df


def calculate_overall_iou_from_df(
    df: pd.DataFrame,
    exclude_columns: Iterable[str] = ["global_step", "batch_idx", "background"],
) -> pd.DataFrame:
    """calculate overall IOU from a dataframe with IOU values.

    # TODO: the dataframe has to have the following layout

    Parameters
    ----------
    df : pd.DataFrame
        dataframe to calculate the IOU of
    exclude_columns: Iterable[str]
        column names to NOT take the mean over


    Examples
    --------

        A = np.ones((10, 10), dtype=np.int)
        B = np.ones((10, 10), dtype=np.int)
        B[:5, :5] = 0
        B[5:, 5:] = 1
        B[5:, :5] = 2

        predicted = np.stack([A] * 10, axis=0)
        target = np.stack([B] * 10, axis=0)
        label_names = ["zeros", "ones", "twos", "threes"]
        df = calculate_iou_df(predicted, target, label_names)
        df_mean = calculate_overall_iou_from_df(df)

        print(df_mean)
        >>> batch_idx  zeros  ones  twos  threes   overall
        >>> 4.5    0.0   0.5   0.0     NaN  0.166667

    """

    df_mean = df[df != -1].mean().to_frame().transpose()
    df_mean["overall"] = df_mean[
        filter(lambda x: x not in exclude_columns, df.columns)
    ].mean(axis=1)
    return df_mean


def get_best_segmentation(
    groundtruth_segmentation, inferred_segmentation, dp_remap_dict
):
    """
    # TODO: document this
    [N, H, W], [N, H, W]

    --> returns [N, H, W], [N, H, W]
    """
    remapped_gt_segmentation = remap_parts(groundtruth_segmentation, dp_remap_dict)

    best_remapping = compute_best_iou_remapping(
        inferred_segmentation, remapped_gt_segmentation
    )
    remapped_inferred = remap_parts(inferred_segmentation, best_remapping)

    return remapped_gt_segmentation, remapped_inferred


warnings.warn("PART_DICT_ID2STR changed", Warning)
PART_DICT_ID2STR = {
    0: "background",
    1: "back",
    2: "chest",
    3: "right_hand",
    4: "left_hand",
    5: "left_foot",
    6: "right_foot",
    7: "back_upper_front_leg",
    8: "back_upper_left_leg",
    9: "right_upper_leg",
    10: "left_upper_leg",
    11: "back_right_lower_leg",
    12: "back_left_lower_leg",
    13: "right_lower_leg",
    14: "left_lower_leg",
    15: "left_upper_arm1",
    16: "right_upper_arm1",
    17: "left_upper_arm2",
    18: "right_upper_arm2",
    19: "left_lower_arm1",
    20: "right_lower_arm1",
    21: "left_lower_arm2",
    22: "right_lower_arm2",
    23: "left_head",
    24: "right_head",
}

PART_LIST = list(PART_DICT_ID2STR.values())
