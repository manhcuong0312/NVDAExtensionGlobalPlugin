# globalPlugins\NVDAExtensionGlobalPlugin\browseModeEx\UIAParagraph.py
# A part of NVDAExtensionGlobalPlugin add-on
# Copyright (C) 2018 - 2020 paulber19
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import browseMode
import UIAHandler
import textInfos
from UIAUtils import getUIATextAttributeValueFromRange


def UIAParagraphQuicknavIterator(document, position, direction="next"):
	if position:
		curPosition = position
	else:
		curPosition = document.makeTextInfo(
			textInfos.POSITION_LAST if direction == "previous"
			else textInfos.POSITION_FIRST)
	stop = False
	firstLoop = True
	while not stop:
		tempInfo = curPosition.copy()
		tempInfo.expand(textInfos.UNIT_CHARACTER)
		styleIDValue = getUIATextAttributeValueFromRange(
			tempInfo._rangeObj, UIAHandler.UIA_StyleIdAttributeId)
		if styleIDValue == UIAHandler.StyleId_Normal:
			if not firstLoop or not position:
				tempInfo.expand(textInfos.UNIT_PARAGRAPH)
				yield browseMode.TextInfoQuickNavItem("paragraph", document, tempInfo)
		stop = (curPosition.move(
			textInfos.UNIT_PARAGRAPH,
			1 if direction == "next" else -1) == 0)
		firstLoop = False
