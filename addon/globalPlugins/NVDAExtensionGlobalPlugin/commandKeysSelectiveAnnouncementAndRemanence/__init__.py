# globalPlugins\NVDAExtensionGlobalPlugin\commandKeysSelectiveAnnouncementAndRemanence\__init__.py
# A part of NVDAExtensionGlobalPlugin add-on
# Copyright (C) 2018 - 2020 paulber19
# This file is covered by the GNU General Public License.
# See the file COPYING for more details.

import addonHandler
from logHandler import log
import scriptHandler
import speech
import gui
import controlTypes
import inputCore
import watchdog
import queueHandler
import api
import wx
import config
import sayAllHandler
import time
from vkCodes import byName
import ui
import tones
import core
from inputCore import NoInputGestureAction
from ..utils.NVDAStrings import NVDAString
from ..utils import speakLater, makeAddonWindowTitle
from ..settings import _addonConfigManager, toggleOnlyNVDAKeyInRemanenceAdvancedOption, toggleBeepAtRemanenceStartAdvancedOption, toggleBeepAtRemanenceEndAdvancedOption, isInstall  # noqa:E501
from ..settings.addonConfig import ID_KeyRemanence
from ..utils.keyboard import getKeyboardKeys
from ..utils.py3Compatibility import py3
from keyboardHandler import KeyboardInputGesture
from . import specialForGmail
addonHandler.initTranslation()

_NVDA_InputManager = None
_myInputManager = None


_availableModifierKeysCombination = [
	["NVDA", ],
	["NVDA", "alt"],
	["NVDA", "alt", "control"],
	["NVDA", "alt", "control", "shift"],
	["NVDA", "alt", "shift"],
	["NVDA", "control"],
	["NVDA", "control", "shift"],
	["NVDA", "shift"],
	["alt", ],
	["alt", "control"],
	["alt", "control", "shift"],
	["alt", "shift"],
	["control", ],
	["control", "shift"],
	["shift", ],
	]


class MyInputManager (inputCore.InputManager):
	# gesture's sequence to set remanence's activation
	activationSequences = [
		"rightShift,rightControl,rightShift",
		"leftShift,leftControl,leftShift",
		]
	# to save last modifiers used for activation setting
	lastModifiersForActivation = []
	# remanence timer
	remanenceTimer = None
	remanenceActivation = False
	lastModifiers = []
	lastGesture = None
	lastModifierForRepeat = []
	lastGestureTime = None
	enableNumpadNnavigationKeys = False

	def __init__(self):
		self.commandKeysFilter = CommandKeysFilter()
		from ..settings import _addonConfigManager
		self.taskTimer = None
		if _addonConfigManager.getRemanenceAtNVDAStart():
			self.taskTimer = wx.CallLater(4000, self.toggleRemanenceActivation)
		self.hasPreviousRemanenceActivationOn = False
		super(MyInputManager, self).__init__()
		from ..settings import toggleEnableNumpadNavigationModeToggleAdvancedOption, toggleActivateNumpadNavigationModeAtStartAdvancedOption  # noqa:E501
		if (
			toggleEnableNumpadNavigationModeToggleAdvancedOption(False)
			and toggleActivateNumpadNavigationModeAtStartAdvancedOption(False)):
			self.setNumpadNavigationMode(True)
		self.NVDAExecuteGesture = _NVDA_InputManager .executeGesture

	def stopRemanence(self, beep=False):
		if self.remanenceActivation is False:
			return
		self.lastModifiers = []
		if self.isRemanenceStarted():
			self.remanenceTimer.Stop()
		self.remanenceTimer = None
		if beep and toggleBeepAtRemanenceEndAdvancedOption(False):
			tones.beep(3000, 20)

	def startRemanence(self, gesture):
		def endRemanence(gesture):
			self.stopRemanence(beep=True)
			if gesture.isNVDAModifierKey:
				gesture.noAction = True
			else:
				gesture.noAction = False
			queueHandler.queueFunction(
				queueHandler.eventQueue, self.executeNewGesture, gesture)
		if self.remanenceActivation is False:
			return
		if not self.isRemanenceStarted():
			if toggleBeepAtRemanenceStartAdvancedOption(False):
				tones.beep(100, 60)
		else:
			self.remanenceTimer.Stop()
		self.remanenceTimer = core.callLater(
			_addonConfigManager.getRemanenceDelay(), endRemanence, gesture)

	def isRemanenceStarted(self):
		if self.remanenceTimer is not None:

			return True
		return False

	def toggleRemanenceActivation(self):
		if self.taskTimer is not None:
			self.taskTimer.Stop()
			self.TaskTimer = None
		if self.remanenceActivation is False:
			self.remanenceActivation = True
			if (
				_addonConfigManager.getRemanenceAtNVDAStart()
				and not self.hasPreviousRemanenceActivationOn):
				# don's say first activation
				msg = None
				self.hasPreviousRemanenceActivationOn = True
			else:
				# Translators: message to user to report keys remanence is on.
				msg = _("Keys's remanence activation on")
			specialForGmail.initialize()
		else:
			self.stopRemanence()
			self.remanenceActivation = False
			# Translators: message to user to report keys remanence is off.
			msg = _("Keys's remanence activation off")
			specialForGmail.terminate()
		curAddon = addonHandler.getCodeAddon()
		addonSummary = curAddon.manifest['summary']
		if msg is not None:
			queueHandler.queueFunction(
				queueHandler.eventQueue,
				ui.message,
				"%s - %s" % (addonSummary, msg))
			core.callLater(30, speech.speakMessage, "%s - %s" % (addonSummary, msg))
	def manageRemanenceActivation(self, gesture):
		if not gesture.isModifier:
			# it's not a modifier key,
			# so forget all previous saved modifiers for activation.
			self.lastModifiersForActivation = []
			return False
		# only modifier key can be in activation sequence
		self.lastModifiersForActivation.append(gesture)
		if len(self.lastModifiersForActivation) > 5:
			self.lastModifiersForActivation = self.lastModifiersForActivation[1:]
		if len(self.lastModifiersForActivation) < 3:
			return False
		tempList = self.lastModifiersForActivation[-3:]
		s = ""
		for modifier in tempList:
			s = s+","+modifier.mainKeyName
		if s[1:] not in self.activationSequences:
			return False
		self.lastModifiersForActivation = []
		self.toggleRemanenceActivation()
		self.stopRemanence()
		return True

	def isRemanenceKey(self, gesture):
		if (
			toggleOnlyNVDAKeyInRemanenceAdvancedOption(False)
			and gesture.mainKeyName.lower() == "nvda"
			or not toggleOnlyNVDAKeyInRemanenceAdvancedOption(False)
			and gesture.isModifier):
			return True
		return False

	def manageRemanence(self, currentGesture):
		if not isInstall(ID_KeyRemanence):
			return None
		delayBetweenGestures = time.time() - self.lastGestureTime\
			if self.lastGestureTime else time.time()
		self.lastGestureTime = time.time()
		lastGesture = self.lastGesture
		self.lastGesture = currentGesture
		if self.manageRemanenceActivation(currentGesture):
			return None
		if not self.remanenceActivation:
			return None
		if self.isRemanenceKey(currentGesture):
			# if gesture is the same than last saved modifier , stop remanence
			if self.isRemanenceStarted()\
				and len(self.lastModifiers)\
				and currentGesture.displayName == self.lastModifiers[-1].displayName:
				self.stopRemanence(beep=True)
				return None
			self.lastModifiers.append(currentGesture)
			queueHandler.queueFunction(
				queueHandler.eventQueue, self.startRemanence, currentGesture)
			if not currentGesture.isNVDAModifierKey:
				currentGesture.noAction = True
			return None
		if (currentGesture.mainKeyName.lower() == "capslock"):
			self.stopRemanence()
		if not self.isRemanenceStarted():
			# perhaps it's a gesture repeat
			if (
				(delayBetweenGestures > 0.5)
				or lastGesture is None
				or (
					lastGesture and (currentGesture.displayName) != lastGesture.displayName)
			):
				# no, it's a normal gesture
				self.lastModifiersForRepeat = []
				return None
		else:
			if currentGesture.isModifier:
				self.lastModifiers.append(currentGesture)
				currentGesture.noAction = True
				return None
			# remanence is started, so saved last modifiers for repeat
			self.lastModifiersForRepeat = self.lastModifiers[:]
			self.stopRemanence()
		if len(self.lastModifiersForRepeat) == 0:
			return None

		# calculate new gesture with all saved modifier keys
		modifiers = set()
		for modifier in self.lastModifiersForRepeat:
			modifiers.add((modifier.vkCode, modifier.isExtended))
		vkCode = currentGesture.vkCode
		scanCode = currentGesture.scanCode
		extended = currentGesture.isExtended
		newGesture = KeyboardInputGesture(modifiers, vkCode, scanCode, extended)
		return newGesture

	def executeNewGesture(self, gesture):
		try:
			self.executeKeyboardGesture(gesture, bypassRemanence=True)
		except inputCore.NoInputGestureAction:
			gesture.send()
		except:  # noqa:E722
			log.error("internal_keyDownEvent", exc_info=True)

	def setNumpadNavigationMode(self, state):
		self.enableNumpadNnavigationKeys = state
		if state:
			# unbind nvda object navigation script keystroke bound to numpad keys
			numpadKeyNames = ["kb:numpad%s" % str(x) for x in range(1, 10)]
			numpadKeyNames.extend(
				["kb:control+numpad%s" % str(x) for x in range(1, 10)])
			numpadKeyNames.extend(["kb:shift+numpad%s" % str(x) for x in range(1, 10)])
			numpadKeyNames .extend(
				["kb:numpadMultiply", "kb:numpadDivide", "kb:numpadPlus"])
			numpadKeyNames .extend(["kb:control+numpadMultiply", "kb:control+numpadDivide", "kb:control+numpadPlus"])  # noqa:E501
			numpadKeyNames .extend(["kb:shift+numpadMultiply", "kb:shift+numpadDivide", "kb:shift+numpadPlus"])  # noqa:E501
			d = {"globalCommands.GlobalCommands": {
				"None": numpadKeyNames}}
			self.localeGestureMap.update(d)
		else:
			self.loadLocaleGestureMap()

	def toggleNavigationNumpadMode(self):
		state = not self.enableNumpadNnavigationKeys
		self.setNumpadNavigationMode(state)
		if state:
			# Translators: message to user to report numpad navigation mode change.
			msg = _("Standard use of the numeric keypad enabled")
		else:
			# Translators: message to user to report numpad navigation mode change.
			msg = _("Standard use of the numeric keypad disabled")
		queueHandler.queueFunction(queueHandler.eventQueue, speech.speakMessage, msg)

	def getNumpadKeyReplacement(self, gesture):
		if not self.enableNumpadNnavigationKeys:
			return None
		if gesture.isModifier or "nvda" in gesture.displayName.lower():
			# excluded modifier key and numpad keys with NVDA modifiers
			return None
		numpadKeyNames = ["numpad%s" % str(x) for x in range(1, 10)]
		numpadKeyNames.remove("numpad5")
		if gesture.mainKeyName in numpadKeyNames:
			vkCode = gesture.vkCode
			scanCode = gesture.scanCode
			extended = not gesture.isExtended
			newGesture = KeyboardInputGesture(gesture.modifiers, vkCode, scanCode, extended)  # noqa:E501
			return newGesture
		return None

	def executeKeyboardGesture(self, gesture, bypassRemanence=False):
		"""Perform the action associated with a gesture.
		@param gesture: The gesture to execute
		@type gesture: L{InputGesture}
		@raise NoInputGestureAction: If there is no action to perform.
		"""
		if not hasattr(gesture, "noAction"):
			gesture.noAction = False
		if watchdog.isAttemptingRecovery:
			# The core is dead, so don't try to perform an action.
			# This lets gestures pass through unhindered where possible,
			# as well as stopping a flood of actions when the core revives.
			raise NoInputGestureAction
		newGesture = self.manageRemanence(gesture) if not bypassRemanence else None
		if newGesture is not None:
			queueHandler.queueFunction(
				queueHandler.eventQueue, self.executeNewGesture, newGesture)
			return
		newGesture = self.getNumpadKeyReplacement(gesture)
		if newGesture is not None:
			queueHandler.queueFunction(
				queueHandler.eventQueue, self.executeNewGesture, newGesture)
			return
		script = gesture.script
		focus = api.getFocusObject()
		if focus.sleepMode is focus.SLEEP_FULL\
			or (focus.sleepMode and not getattr(script, 'allowInSleepMode', False)):
			raise NoInputGestureAction
		wasInSayAll = False
		if gesture.isModifier:
			if not self.lastModifierWasInSayAll:
				wasInSayAll = self.lastModifierWasInSayAll = sayAllHandler.isRunning()
		elif self.lastModifierWasInSayAll:
			wasInSayAll = True
			self.lastModifierWasInSayAll = False
		else:
			wasInSayAll = sayAllHandler.isRunning()
		if wasInSayAll:
			gesture.wasInSayAll = True
		speechEffect = gesture.speechEffectWhenExecuted
		if speechEffect == gesture.SPEECHEFFECT_CANCEL:
			queueHandler.queueFunction(queueHandler.eventQueue, speech.cancelSpeech)
		elif speechEffect in (gesture.SPEECHEFFECT_PAUSE, gesture.SPEECHEFFECT_RESUME):  # noqa:E501
			queueHandler.queueFunction(
				queueHandler.eventQueue,
				speech.pauseSpeech,
				speechEffect == gesture.SPEECHEFFECT_PAUSE)
		if py3 and gesture.shouldPreventSystemIdle:
			winKernel.SetThreadExecutionState(
				winKernel.ES_SYSTEM_REQUIRED | winKernel.ES_DISPLAY_REQUIRED)
		if log.isEnabledFor(log.IO) and not gesture.isModifier:
			self._lastInputTime = time.time()
			log.io("Input: %s" % gesture.identifiers[0])
		if self._captureFunc:
			try:
				if self._captureFunc(gesture) is False:
					return
			except:  # noqa:E722
				log.error("Error in capture function, disabling", exc_info=True)
				self._captureFunc = None
		if gesture.isModifier:
			if gesture.noAction:
				gesture.normalizedModifiers = []
				return
			raise NoInputGestureAction
		self.speakGesture(gesture)
		if not script:
			gesture.reportExtra()
		# then queue all following gestures
			# (that don't have a script
			# ) with a fake script so that they remain in order.
		if not script and (
			bypassRemanence
			or scriptHandler._numIncompleteInterceptedCommandScripts):
			script = lambda gesture: gesture.send()  # noqa:E731
		if script:
			scriptHandler.queueScript(script, gesture)
			return
		raise NoInputGestureAction

	def executeGesture(self, gesture):
		try:
			if isinstance(gesture, KeyboardInputGesture):
				self.executeKeyboardGesture(gesture)
			else:
				self.NVDAExecuteGesture(gesture)
		except NoInputGestureAction:
			raise NoInputGestureAction

	def speakGesture(self, gesture):
		if not gesture.shouldReportAsCommand:
			return
		if self.commandKeysFilter.canSpeakGesture(gesture):
			queueHandler.queueFunction(
				queueHandler.eventQueue, speech.speakMessage, gesture.displayName)


class CommandKeysFilter(object):
	def __init__(self):
		pass

	def checkModifiers(self, modifiers, keyLabel):
		index = -1
		for item in _availableModifierKeysCombination:
			if set(modifiers) == set(item):
				index = _availableModifierKeysCombination.index(item)
				break
		if index >= 0:
			mask = int(self.keysDic[keyLabel.lower()])

			if not mask & (2 ** index):
				return False
		return True

	def canSpeakGesture(self, gesture):
		speakCommandKeysOption = config.conf["keyboard"]["speakCommandKeys"]
		self.keysDic = _addonConfigManager.getCommandKeysSelectiveAnnouncement(
			speakCommandKeysOption)
		self.keys = []
		for key in self.keysDic:
			if int(self.keysDic[key]):
				self.keys.append(key)
		try:
			modifiers = gesture._get_modifierNames()
			keyLabel = gesture._get_mainKeyName()
		except:  # noqa:E722
			return True

		if not speakCommandKeysOption:
			if keyLabel.lower() in self.keys:
				return self.checkModifiers(modifiers, keyLabel)
			else:
				return False
		else:
			if keyLabel.lower() in self.keys:
				return not self.checkModifiers(modifiers, keyLabel)
			else:
				return True
		return True

	def updateCommandKeysSelectiveAnnouncement(
		self, keys, speakCommandKeysOption):
		_addonConfigManager.saveCommandKeysSelectiveAnnouncement(
			keys, speakCommandKeysOption)


class CommandKeysSelectiveAnnouncementDialog(gui.SettingsDialog):
	# Translators: title for the Command Keys Selective Announcement Dialog.
	title = _("Command keys selective Announcement")

	def __init__(self, parent):
		self.title = makeAddonWindowTitle(self.title)
		super(CommandKeysSelectiveAnnouncementDialog, self).__init__(parent)

	def listInit(self):
		self.keysDic = _addonConfigManager.getCommandKeysSelectiveAnnouncement(
			self.speakCommandKeysOption)
		self.NVDAKeys = [x for x in byName]
		from keyLabels import localizedKeyLabels
		self.localizedKeyboardKeyNames = []
		self.keyboardKeys = {}
		for key in self.NVDAKeys:
			if self.isModifier(key):
				continue
			if key in localizedKeyLabels:
				label = localizedKeyLabels[key]
			else:
				label = key
			self.localizedKeyboardKeyNames.append(label)
			self.keyboardKeys[label] = key
		self.localizedKeyboardKeyNames.sort()
		for key in self._keyboardKeys:
			self.localizedKeyboardKeyNames.append(key)

	def modifierKeysCombinationListInit(self):
		from keyLabels import localizedKeyLabels
		self.modifierKeys = []
		for item in _availableModifierKeysCombination:
			modifiers = ""
			for key in item:
				label = localizedKeyLabels[key] if key in localizedKeyLabels else key
				modifiers = modifiers + " + " + label
			modifiers = modifiers[1:]
			self.modifierKeys.append(modifiers)

	def updateCheckedKeys(self):
		keys = [x for x in self.keysDic]
		for index in range(0, self.keyboardKeysListBox.GetCount()):
			label = self.keyboardKeysListBox.GetString(index)
			key = label
			if label in self.keyboardKeys:
				key = self.keyboardKeys[label]
			if key in keys and int(self.keysDic[key]):
				self.keyboardKeysListBox.Check(index)

	def updateModifierKeysList(self, key):
		modifierKeys = int(self.keysDic[key])
		for i in range(0, len(_availableModifierKeysCombination)):
			mask = 2 ** i
			if modifierKeys & mask:
				self.modifierKeysListBox.Check(i)
		self.modifierKeysListBox.SetSelection(0)

	def makeSettings(self, settingsSizer):
		# init
		self._keyboardKeys = getKeyboardKeys()
		self.noChange = True
		self.speakCommandKeysOption = config.conf["keyboard"]["speakCommandKeys"]
		self.listInit()
		self.modifierKeysCombinationListInit()
		# gui
		sHelper = gui.guiHelper.BoxSizerHelper(self, sizer=settingsSizer)
		# the speak command key flag
		self.commandKeysCheckBox = sHelper.addItem(wx.CheckBox(
			self,
			wx.ID_ANY,
			label=NVDAString("Speak command &keys")))
		self.commandKeysCheckBox.SetValue(
			config.conf["keyboard"]["speakCommandKeys"])
		# the keyboard key list box
		# Translators: This is a label appearing
		# on Command Keys Selective Announcement Dialog.
		keyboardKeysListText = _("Check &excluded keys:")
		self.keyboardKeysListBox_ID = wx.NewIdRef()
		self.keyboardKeysListBox = sHelper.addLabeledControl(
			keyboardKeysListText,
			wx.CheckListBox,
			id=self.keyboardKeysListBox_ID,
			name="KeyboardKeysList",
			choices=self.localizedKeyboardKeyNames,
			style=wx.LB_SINGLE | wx.WANTS_CHARS)
		if self.keyboardKeysListBox.GetCount():
			self.keyboardKeysListBox.SetSelection(0)

		# the modifiers keys list box
		# Translators: This is a label appearing
		# on Command Keys Selective Announcement Dialog.
		modifierKeysListLabelText = _("W&ith key combination:")
		try:
			self.modifierKeysListBox_ID = wx.NewIdRef()
		except:  # noqa:E722
			self.modifierKeysListBox_ID = wx.NewId()
		self.modifierKeysListBox = sHelper.addLabeledControl(
			modifierKeysListLabelText,
			wx.CheckListBox,
			id=self.modifierKeysListBox_ID,
			name="ModifierKeysList",
			choices=self.modifierKeys,
			style=wx.LB_SINGLE | wx.WANTS_CHARS)
		if self.modifierKeysListBox.GetCount():
			self.modifierKeysListBox.SetSelection(0)
		# Events
		self.commandKeysCheckBox.Bind(
			wx.EVT_CHECKBOX, self.onCheckCommandKeysCheckBox)
		self.keyboardKeysListBox.Bind(wx.EVT_LISTBOX, self.onSelectKey)
		self.keyboardKeysListBox.Bind(wx.EVT_CHECKLISTBOX, self.onCheckListBox)
		self.keyboardKeysListBox.Bind(wx.EVT_KEY_DOWN, self.onKeydown)
		self.keyboardKeysListBox.Bind(wx.EVT_SET_FOCUS, self.focusOnCommandKey)
		self.modifierKeysListBox.Bind(
			wx.EVT_LISTBOX, self.onSelectModifierKeysCombination)
		self.modifierKeysListBox.Bind(wx.EVT_CHECKLISTBOX, self.onCheckModifierKey)
		self.modifierKeysListBox.Bind(wx.EVT_KEY_DOWN, self.onKeydown)
		self.modifierKeysListBox.Bind(
			wx.EVT_SET_FOCUS, self.focusOnModifierKeysCombination)
		self.updateCheckedKeys()

	def postInit(self):
		self.commandKeysCheckBox.SetFocus()

	def reportCheckedState(self, checked=True):
		stateText = controlTypes.stateLabels[controlTypes.STATE_CHECKED] if checked\
			else controlTypes.negativeStateLabels[controlTypes.STATE_CHECKED]
		wx.CallLater(
			300,
			queueHandler.queueFunction,
			queueHandler.eventQueue,
			speech.speakMessage,
			stateText)

	def onCheckCommandKeysCheckBox(self, evt):
		self.speakCommandKeysOption = self.commandKeysCheckBox.GetValue()
		modeText = NVDAString("Speak command &keys")\
			if not self.speakCommandKeysOption else _("Do not speak command &keys")
		res = not self.noChange and gui.messageBox(
			# Translators: the text of a message box dialog
			# in Command keys selective announcement dialog.
			_("""Do you want save changes made in "%s" mode""") % modeText,
			# Translators: the title of a message box dialog
			# in command keys selective announcement dialog.
			_("Confirmation"),
			wx.OK | wx.NO | wx.CANCEL | wx.ICON_WARNING)
		if res == wx.CANCEL:
			return
		elif res == wx.OK:
			_myInputManager.commandKeysFilter.updateCommandKeysSelectiveAnnouncement(
				self.keysDic, not speakCommandKeysOption)
		self.listInit()
		self.keyboardKeysListBox.SetItems(self.localizedKeyboardKeyNames)
		self.keyboardKeysListBox.SetSelection(0)
		self.updateCheckedKeys()
		self.noChange = True
		evt.Skip()

	def onSelectKey(self, evt):
		index = self.keyboardKeysListBox.GetSelection()
		if index >= 0 and self.keyboardKeysListBox.IsChecked(index):
			self.reportCheckedState()
			label = self.keyboardKeysListBox.GetStringSelection()
			key = label
			if label in self.keyboardKeys:
				key = self.keyboardKeys[label]
			self.updateModifierKeysList(key)
			self.modifierKeysListBox.Enable()
		elif index >= 0:
			speakLater()
			self.modifierKeysListBox.SetItems(self.modifierKeys)
			self.modifierKeysListBox.Disable()

	def onSelectModifierKeysCombination(self, evt):
		index = self.modifierKeysListBox.GetSelection()
		if index >= 0 and self.modifierKeysListBox.IsChecked(index):
			self.reportCheckedState()
		else:
			speakLater()

	def focusOnCommandKey(self, evt):
		self.onSelectKey(evt)

	def focusOnModifierKeysCombination(self, evt):
		self.onSelectModifierKeysCombination(evt)

	def isModifier(self, key):
		modifierKeys = [
			"nvda",
			"alt", "rightalt", "leftalt",
			"control", "rightcontrol", "leftcontrol",
			"shift", "rightshift", "leftshift"]
		if key.lower() in modifierKeys:
			return True
		return False

	def onCheckListBox(self, evt):
		index = self.keyboardKeysListBox.GetSelection()
		label = self.keyboardKeysListBox.GetStringSelection()
		key = label
		if label in self.keyboardKeys:
			key = self.keyboardKeys[label]
		if self.keyboardKeysListBox.IsChecked(index):
			self.reportCheckedState()
			mask = int()
			for i in range(0, len(_availableModifierKeysCombination)):
				mask = mask + (2 ** i)
			mask = mask + (2 ** len(_availableModifierKeysCombination))
			self.keysDic[key] = mask
			self.updateModifierKeysList(key)
			self.modifierKeysListBox.Enable()
		else:
			self.keysDic[key] = int(0)
			self.reportCheckedState(False)
			self.modifierKeysListBox.SetItems(self.modifierKeys)
			self.modifierKeysListBox.Disable()
		self.noChange = False
		evt.Skip()

	def onCheckModifierKey(self, evt):
		index = self.modifierKeysListBox.GetSelection()
		label = self.keyboardKeysListBox.GetStringSelection()
		key = label
		if label in self.keyboardKeys:
			key = self.keyboardKeys[label]
		if self.modifierKeysListBox.IsChecked(index):
			self.keysDic[key] = int(self.keysDic[key]) | (int(2 ** index))
			self.reportCheckedState()
		else:
			mask = ~(2 ** index)
			self.keysDic[key] = int(self.keysDic[key]) & mask
			self.reportCheckedState(False)
		self.noChange = False
		evt.Skip()

	def onKeydown(self, evt):
		keyCode = evt.GetKeyCode()
		id = evt.GetId()
		if keyCode == wx.WXK_F1:  # 340
			# go to next checked key
			if id == self.keyboardKeysListBox_ID:
				tempList = self.keyboardKeysListBox
				onSelect = self.onSelectKey
			elif id == self.modifierKeysListBox_ID:
				tempList = self.modifierKeysListBox
				onSelect = self.onSelectModifierKeysCombination
			index = tempList.GetSelection()
			count = tempList.GetCount()
			if index < count - 1:
				for i in range(index+1, count):
					if tempList.IsChecked(i):
						tempList.SetSelection(i)
						onSelect(evt)
						return
			# Translators: message to user when there is no more checked command key.
			speakLater(300, _("No more checked command key"))
			return
		if keyCode == wx.WXK_F2:  # 341
			# go to previous checked key
			if id == self.keyboardKeysListBox_ID:
				tempList = self.keyboardKeysListBox
				onSelect = self.onSelectKey
			elif id == self.modifierKeysListBox_ID:
				tempList = self.modifierKeysListBox
				onSelect = self.onSelectModifierKeysCombination
			index = tempList.GetSelection()
			if index > 0:
				while index > 0:
					index = index-1
					if tempList.IsChecked(index):
						tempList.SetSelection(index)
						onSelect(evt)
						return
			# Translators: message to user when there is no more checked command key .
			speakLater(300, _("No more checked command key"))
			return
		if keyCode == wx.WXK_TAB:
			shiftDown = evt.ShiftDown()
			if shiftDown:
				wx.Window.Navigate(
					self.keyboardKeysListBox, wx.NavigationKeyEvent.IsBackward)
			else:
				wx.Window.Navigate(
					self.keyboardKeysListBox, wx.NavigationKeyEvent.IsForward)
			return
		if keyCode == wx.WXK_RETURN and (
			id == self.keyboardKeysListBox_ID
			or id == self.modifierKeysListBox_ID):
			self.onOk(evt)
			return
		evt.Skip()

	def onOk(self, evt):
		speakCommandKeysOption = self.commandKeysCheckBox.GetValue()
		_myInputManager.commandKeysFilter.updateCommandKeysSelectiveAnnouncement(
			self.keysDic, speakCommandKeysOption)
		super(CommandKeysSelectiveAnnouncementDialog, self).onOk(evt)


def initialize():
	global _NVDA_InputManager, _myInputManager
	_NVDA_InputManager = inputCore.manager
	_myInputManager = MyInputManager()
	_myInputManager ._captureFunc = inputCore.manager._captureFunc
	_myInputManager .localeGestureMap = inputCore.manager.localeGestureMap
	_myInputManager .userGestureMap = inputCore.manager.userGestureMap
	_myInputManager._lastInputTime = inputCore.manager._lastInputTime
	_myInputManager.lastModifierWasInSayAll = inputCore.manager.lastModifierWasInSayAll  # noqa:E501
	inputCore.manager = _myInputManager
	log.warning("commandKeysSelectiveAnnouncementAndRemanence initialized")


def terminate():
	global _NVDA_InputManager, _myInputManager
	if _NVDA_InputManager is not None:
		inputCore.manager = _NVDA_InputManager
	_myInputManager = None
	specialForGmail.terminate()
