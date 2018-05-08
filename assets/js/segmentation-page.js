import * as ah from './audio-handler';
import * as fg from 'flexible-grid';
import * as vs from 'visualise-d3';
import {defaultGridOptions} from './flexible-grid';
import {deepCopy, getUrl, setCache, getCache} from './utils';
import {postRequest} from './ajax-handler';
require('bootstrap-slider/dist/bootstrap-slider.js');
const keyboardJS = require('keyboardjs/dist/keyboard.min.js');

const gridOptions = deepCopy(defaultGridOptions);

let ce;

class Grid extends fg.FlexibleGrid {
    init() {
        super.init({
            'grid-name': 'segments-grid',
            'grid-type': 'segments-grid',
            gridOptions
        });
    }

    /**
     * Highlight the active row on mouse over (super) and also highlight the corresponding segment on the spect
     * @param e
     * @param args
     */
    mouseHandler(e, args) {
        super.mouseHandler(e, args);

        const self = this;
        let eventType = e.type;
        let grid = args.grid;
        let dataView = grid.getData();
        let cell = grid.getCellFromEvent(e);
        let row = cell.row;
        let rowElement = $(e.target.parentElement);
        let songId = dataView.getItem(row).id;
        self.eventNotifier.trigger(eventType, {
            songId,
            rowElement
        });
    }

    /**
     * Highlight the owner's measurement in the segmentation table when the corresponding spectrogram owner is mouseover
     * @param args indexed array {event: name of the event, target: the element that is being mouseover}
     */
    segmentMouseEventHandler(e, args) {
        const self = this;
        let eventType = args.type;
        let target = args.target;
        let dataView = self.mainGrid.getData();
        let sylId = target.getAttribute('syl-id');
        let sylIdx = dataView.getIdxById(sylId);

        /*
         * Scroll the table to this position, this is necessary because if the cell is currently overflow, getCellNode()
         * will return undefined.
         */
        self.mainGrid.gotoCell(sylIdx, 0);
        self.mainGrid.scrollCellIntoView(sylIdx, 0);
        let cellElement = self.mainGrid.getCellNode(sylIdx, 0);
        if (cellElement) {
            let rowElement = $(cellElement.parentElement);

            if (eventType === 'segment-mouseover') {
                rowElement.addClass('highlight');
            }
            else if (eventType === 'segment-mouseleave') {
                rowElement.removeClass('highlight');
            }
        }
    }

    /**
     * Change the syllable table when a new syllable is drawn or an existing one is adjusted (incl. deletion)
     * from the spectrogram
     * @param args
     */
    segmentChangeEventHandler(e, args) {
        const self = this;
        let eventType = args.type;
        let target = args.target;
        let dataView = self.mainGrid.getData();

        saveSegmentationBtn.prop('disabled', false);

        if (eventType === 'segment-created') {
            dataView.addItem(target);
        }
        else if (eventType === 'segment-adjusted') {
            dataView.updateItem(target.id, target);
        }
    }

}

const grid = new Grid();
const gridEl = $('#segments-grid');
const fileId = gridEl.attr('file-id');
const fileLength = gridEl.attr('length');
const fileFs = gridEl.attr('fs');
const speedSlider = $('#speed-slider');
const spectrogramId = 'spectrogram';
const viz = new vs.Visualise();
const saveSegmentationBtn = $('#save-segmentations-btn');
const deleteSegmentsBtn = $('#delete-segments-btn');

export const visualiseSong = function (callback) {

    /*
     * Clear all temporary variables
     */
    setCache('resizeable-syl-id', undefined);
    setCache('syllables', {});

    let data = new FormData();
    data.append('file-id', fileId);
    let args = {
        url: getUrl('send-request', 'koe/get-segment-audio'),
        postData: data,
        cacheKey: fileId,
        startSecond: null,
        endSecond: null
    };
    ah.queryAndHandleAudio(args, function (sig) {
        viz.visualise(fileId, sig);
        callback();
    });
};

export const highlightSegments = function (e, args) {
    let eventType = e.type;
    let songId = args.songId;
    let segmentsGridRowElement = args.rowElement;

    let spectrogramSegment = $('#' + spectrogramId + ' rect.syllable[syl-id="' + songId + '"]');

    if (eventType === 'mouseenter') {
        segmentsGridRowElement.addClass('highlight');
        spectrogramSegment.addClass('highlight');
    }
    else {
        segmentsGridRowElement.removeClass('highlight');
        spectrogramSegment.removeClass('highlight');
    }
};


const initController = function () {
    speedSlider.slider();

    speedSlider.on('slide', function (slideEvt) {
        ah.changePlaybackSpeed(slideEvt.value);
    });

    $('.slider').on('click', function () {
        let newValue = $('.tooltip-inner').text();
        ah.changePlaybackSpeed(parseInt(newValue));
    });

    $('#play-song').click(function () {
        viz.playAudio();
    });

    saveSegmentationBtn.click(function () {
        let items = grid.mainGrid.getData().getItems();
        let postData = {
            items: JSON.stringify(items),
            'file-id': fileId
        };
        let onSuccess = function (rows) {
            grid.deleteAllRows();
            grid.appendRows(rows);

            let syllables = {};
            for (let i = 0; i < rows.length; i++) {
                let item = rows[i];
                syllables[item.id] = item;
            }
            setCache('syllables', syllables);
            viz.displaySegs(rows);
        };
        ce.dialogModal.modal('hide');
        let msgGen = function (res) {
            return res.success ?
                'Success' :
                `Something's wrong. The server says ${res.error}.`;
        };
        postRequest({
            requestSlug: 'koe/save-segmentation',
            data: postData,
            onSuccess,
            msgGen,
            immediate: true
        });
    })
};


/**
 * Allows user to remove songs
 */
const initDeleteSegmentsBtn = function () {
    deleteSegmentsBtn.click(function () {
        let grid_ = grid.mainGrid;
        let selectedRows = grid_.getSelectedRows();
        let numRows = selectedRows.length;
        let dataView = grid_.getData();
        let syllables = getCache('syllables');
        let itemsIds = [];
        for (let i = 0; i < numRows; i++) {
            let item = dataView.getItem(selectedRows[i]);
            itemsIds.push(item.id);
        }

        for (let i = 0; i < numRows; i++) {
            let itemId = itemsIds[i];
            dataView.deleteItem(itemId);
            delete syllables[itemId];
        }

        saveSegmentationBtn.prop('disabled', false);
        viz.displaySegs(syllables);
    });
};


/**
 * Subscribe to this instance of Flexible Grid. This must be called only once when the page loads
 */
const subscribeFlexibleEvents = function () {
    grid.on('mouseenter', highlightSegments);
    grid.on('mouseleave', highlightSegments);

    /**
     * When segments are selected, enable delete button
     */
    function enableDeleteSegmentsBtn() {
        deleteSegmentsBtn.prop('disabled', false);
    }

    /**
     * When segments are removed, if there is songs left, disable the delete button
     * @param e event
     * @param args contains 'grid' - the main SlickGrid
     */
    function disableDeleteSegmentsBtn(e, args) {
        let grid_ = args.grid;
        if (grid_.getSelectedRows().length == 0) deleteSegmentsBtn.prop('disabled', true);
    }

    grid.on('row-added', enableDeleteSegmentsBtn);
    grid.on('rows-added', enableDeleteSegmentsBtn);

    grid.on('row-removed', disableDeleteSegmentsBtn);
    grid.on('rows-removed', disableDeleteSegmentsBtn);

    viz.eventNotifier.on('segment-mouse', function (e, args) {
        grid.segmentMouseEventHandler(e, args);
    });

    viz.eventNotifier.on('segment-changed', function (e, args) {
        grid.segmentChangeEventHandler(e, args);
    });
};


const initKeyboardHooks = function () {
    keyboardJS.bind(
        ['mod', 'ctrl'],
        function () {
            let highlighted = getCache('highlighted-syl-id');

            /* Edit mode on and highlighted. Show brush */
            if (highlighted) {
                viz.showBrush(highlighted);
            }
            viz.editMode = true;
        }, function () {
            viz.clearBrush();
            viz.editMode = false;
        }
    );
};


export const run = function (commonElements) {
    ce = commonElements;

    setCache('file-id', fileId);
    setCache('file-length', fileLength);
    setCache('file-fs', fileFs);

    ah.initAudioContext();
    grid.init(fileId);
    viz.init(spectrogramId);

    visualiseSong(function () {
        grid.initMainGridHeader({
            multiSelect: true,
            '__extra__file_id': fileId
        }, function () {
            grid.initMainGridContent({'__extra__file_id': fileId}, function () {
                let items = grid.mainGrid.getData().getItems();
                let syllables = {};
                for (let i = 0; i < items.length; i++) {
                    let item = items[i];
                    syllables[item.id] = item;
                }
                setCache('syllables', syllables);
                viz.displaySegs(items);
            });
        });
    });
    initController();
    initKeyboardHooks();
    initDeleteSegmentsBtn()
};


export const postRun = function () {
    subscribeFlexibleEvents();
};
