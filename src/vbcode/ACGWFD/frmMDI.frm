VERSION 5.00
Object = "{F74DBB97-4C02-4B5D-AB22-1D7E188F4415}#1.0#0"; "innovadsxp.ocx"
Object = "{F9043C88-F6F2-101A-A3C9-08002B2F49FB}#1.2#0"; "comdlg32.ocx"
Begin VB.Form frmMDI 
   Caption         =   "ACG Workflow Designer"
   ClientHeight    =   8505
   ClientLeft      =   60
   ClientTop       =   345
   ClientWidth     =   10650
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   Icon            =   "frmMDI.frx":0000
   LinkTopic       =   "Form1"
   ScaleHeight     =   8505
   ScaleWidth      =   10650
   StartUpPosition =   3  'Windows Default
   Begin MSComDlg.CommonDialog dlg 
      Left            =   5040
      Top             =   3960
      _ExtentX        =   847
      _ExtentY        =   847
      _Version        =   393216
      CancelError     =   -1  'True
   End
   Begin InnovaDSXP.DockStudio ds 
      Height          =   8505
      Left            =   0
      TabIndex        =   0
      Top             =   0
      Width           =   10650
      _cx             =   18785
      _cy             =   15002
      Object.Bindings        =   "frmMDI.frx":0E42
      BeginProperty Font {0BE35203-8F91-11CE-9DE3-00AA004BB851} 
         Name            =   "Tahoma"
         Size            =   8.25
         Charset         =   0
         Weight          =   400
         Underline       =   0   'False
         Italic          =   0   'False
         Strikethrough   =   0   'False
      EndProperty
      BorderStyle     =   0
      BackColor       =   -2147483633
      EventMode       =   2
      RightToLeft     =   0
      AutoAlignToParent=   -1
      Layout          =   "frmMDI.frx":0ECC
      LastVerbLayoutFilename=   ""
      LanguageFile    =   ""
   End
End
Attribute VB_Name = "frmMDI"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private Const mcstrModule = "frmMDI"
Private WithEvents moContainer As Container
Attribute moContainer.VB_VarHelpID = -1
Private moContextMenu As IContextMenu
'/ dirty,dirty! properties collection used to store all app settings
Private moAppSettings As Properties

'/ task templates collection
Private moTemplates As TaskTemplates
Private moProcessTemplates As ProcessTemplates
Private mAddins As Collection
Public Sub refreshActiveProcess()
    moContextMenu.Refresh
End Sub

Public Property Get activeProcessDef() As ProcessDef
    If moContextMenu Is Nothing Then
        Set activeProcessDef = Nothing
    Else
        Set activeProcessDef = moContextMenu.ProcessDef
    End If
End Property
Private Sub ds_CommandClick(ByVal Command As InnovaDSXP.Command)
    Const cstrFunc = "ds_CommandClick"
    On Error GoTo err_handler
    Dim fHandled As Boolean
    If Not (moContextMenu Is Nothing) Then
        fHandled = moContextMenu.CommandClick(Command)
    End If
    
    If Not fHandled Then
        If Not (Command.Category Is Nothing) Then
            Select Case UCase$(Command.Category.Name)
                Case "FILE"
                    MenuHandlerFile Command
                Case "WINDOW"
                    MenuHandlerWindow Command
                Case "VIEW"
                    MenuHandlerView Command
                
                Case "HELP"
                    MenuHandlerHelp Command
                Case "EDIT"
                    MenuHandlerEdit Command
                Case "ADDINS"
                    menuHandlerAddins Command
                Case Else
                    If Command.Name = "tlUndo" Then
                        MsgBox "oh come on. did you really think i'd go through all the hassle it takes to make an undo command that worked? is the spellcheck, xml configuration, semi-accurate predictive path gubbins, flow to process conversion, categorized property window, pretty colours and ripped off pictures not enough for you?? jeez... get real people.", vbInformation
                    End If
            End Select
            
        End If
    End If
    
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub MenuHandlerView(ByRef Command As InnovaDSXP.Command)
    Dim oTool As InnovaDSXP.CommandToolButton
    Set oTool = Command
    If oTool.State = dsxpCommandToolButtonStateChecked Then
        oTool.State = dsxpCommandToolButtonStateUnchecked
    Else
        oTool.State = dsxpCommandToolButtonStateChecked
    End If
    ds.DockWindows.Item(oTool.Tag).Visible = (oTool.State = dsxpCommandToolButtonStateChecked)
End Sub
Private Sub menuHandlerAddins(ByRef Command As InnovaDSXP.Command)
    Dim oAddin As IAddin
    Set oAddin = CreateObject(Command.Name)
    Dim oAccess As New AddinAccess
    oAccess.init Me
    oAddin.runAddin oAccess
End Sub
Private Sub MenuHandlerWindow(ByRef Command As InnovaDSXP.Command)
    Dim ofrmMDI As frmMDI
    Select Case UCase$(Command.Name)
        Case "TLWINDOWNEW"
            Set ofrmMDI = New frmMDI
            ofrmMDI.Show
    End Select
End Sub

Private Sub MenuHandlerHelp(ByRef Command As InnovaDSXP.Command)
    Dim ofrmMDI As frmMDI
    Select Case UCase$(Command.Name)
        Case "TLABOUT"
            Dim strMsg As String
            strMsg = "Template Path: " & getTemplatePath() & vbCrLf
            strMsg = strMsg & "Version " & App.Major & "." & App.Minor & "." & App.Revision
            MsgBox strMsg
    End Select
End Sub

Private Sub MenuHandlerFile(ByRef Command As InnovaDSXP.Command)
    Dim oFlow As frmFlow
    Dim oDW As DocumentWindow
    Select Case UCase$(Command.Name)
        Case "TLOPEN"
                
            Set oFlow = loadProcess()
            If Not (oFlow Is Nothing) Then
                Set oDW = ds.DocumentWindows.AddForm(CreateGUID, oFlow.getCaption, , oFlow, True)
            End If
        Case "TLSAVE"
        Case "TLNEW"
            MakeNewFlow
        Case "TLEXIT"
        
            Unload Me
        Case "TLBATCHCONVERT"
            Call BatchConvert
        Case "TLCOMBINEVERSIONS"
            Call combineVersions
        Case "TLDOCSCAN"
            Call DocScan
        Case "TLEXPORTIMAGES"
            Call ExportAll
        Case "TLSETTEMPLATEPATH"
            Call SetTemplatePath
    End Select
End Sub

Private Sub SetTemplatePath()
    Dim oBrowse As clShellBrowse
    Set oBrowse = New clShellBrowse
    oBrowse.Caption = "Locate Templates Folder"
    oBrowse.Browse Me.hWnd
    If oBrowse.Cancel Then Exit Sub
    If MsgBox("Change Template Folder from """ & GetSetting(App.Title, basMain.mcstrSettingSection, basMain.mcstrTemplatesPathKey, App.Path & "\Templates\") & """ to """ & oBrowse.Path & "\""?", vbYesNo + vbDefaultButton2 + vbQuestion) = vbNo Then
        Exit Sub
    End If
    SaveSetting App.Title, basMain.mcstrSettingSection, basMain.mcstrTemplatesPathKey, oBrowse.Path & "\"
    MsgBox "Please restart the application for the change to take affect", vbInformation
End Sub

Private Sub MakeNewFlow()
    On Error GoTo err_handler
    Dim oFlow As frmFlow
    Dim oDW As DocumentWindow
    Dim oProcessTemplate As ProcessTemplate
    Const cstrFunc = "MakeNewFlow"
    Dim strErrFunc As String
    
    Set oFlow = New frmFlow
    If moProcessTemplates.Count = 1 Then
        Set oProcessTemplate = moProcessTemplates(1)
    Else
        If Not frmProcessTemplate.ShowChoose(moProcessTemplates, oProcessTemplate) Then
            Unload frmProcessTemplate
            Exit Sub
        End If
        Unload frmProcessTemplate
    End If
    
    Dim oProcess As ProcessDef
    Set oProcess = New ProcessDef
    oProcess.ProcessTemplate = oProcessTemplate.Name
    '/ initialise the process with the property group defaults
    CopyPropGroup oProcessTemplate.ProcessProperties, oProcess.PropertyGroup, False, True
    
    dlg.Filter = "ACG WorkFlow Format|*.acgwfd.xml"
    dlg.FilterIndex = 1
    dlg.DialogTitle = "New Process"
    dlg.fileName = "New " & oProcessTemplate.Name & " Process"
    dlg.Flags = MSComDlg.cdlOFNOverwritePrompt
    On Error Resume Next
    dlg.ShowSave
    If Err.Number <> 0 Then Exit Sub
    On Error GoTo err_handler
    strErrFunc = "Deleting existing file"
    If Len(Dir$(dlg.fileName)) > 0 Then
        Kill dlg.fileName
    End If
    
    strErrFunc = "Exporting new file"
    Dim oExport As XMLProcessVersion
    Set oExport = New XMLProcessVersion
    oProcess.Name = Left$(dlg.FileTitle, Len(dlg.FileTitle) - Len(".acgwfd.xml"))
    Dim oVersions As New Versions
    oExport.FileSaveXML dlg.fileName, oVersions, oProcess
    strErrFunc = "Loading process"
    oFlow.init moContainer, oProcessTemplate, moTemplates, moProcessTemplates
    oFlow.LoadFlow dlg.fileName
    ds.DocumentWindows.AddForm CreateGUID, oProcess.Name, , oFlow, True
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc, strErrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub DocScan()
    Dim oDocScan As DocScan
    Dim oBrowse As clShellBrowse
    Set oBrowse = New clShellBrowse
    oBrowse.Caption = "Select the path to ALL Processes"
    oBrowse.Browse hWnd
    If oBrowse.Cancel Then Exit Sub
    Dim strProcessesPath As String
    strProcessesPath = oBrowse.Path
    oBrowse.Caption = "Select the path to output the Reports to"
    oBrowse.Browse hWnd
    If oBrowse.Cancel Then Exit Sub
    Dim strOutputPath As String
    strOutputPath = oBrowse.Path
    
    
    Set oDocScan = New DocScan
    
    oDocScan.StartScan strProcessesPath, moTemplates, moProcessTemplates, strOutputPath
    MsgBox "Workflow Reporting Complete", vbInformation
End Sub
Private Sub ExportAll()
    Dim oBrowse As clShellBrowse
    Set oBrowse = New clShellBrowse
    oBrowse.Caption = "Select the path to Processes"
    oBrowse.Browse hWnd
    If oBrowse.Cancel Then Exit Sub
    Dim strProcessPath As String
    strProcessPath = oBrowse.Path
    
    oBrowse.Caption = "Select where to place images"
    oBrowse.Browse hWnd
    
    If oBrowse.Cancel Then Exit Sub
    Dim strImagePath As String
    strImagePath = oBrowse.Path
    
    Dim oScan As ACGWFDHelper.ScanPath
    Set oScan = New ACGWFDHelper.ScanPath
    oScan.StartScan strProcessPath & "\", ".acgwfd.xml"
    Dim oFlow As frmFlow
    Do Until oScan.FileList.Count = 0
        Set oFlow = LoadFromFile(oScan.FileList(1), False)
        If (oFlow Is Nothing) Then
            MsgBox "Could not load " & oScan.FileList(1), vbExclamation
        Else
            oFlow.SaveImage strImagePath & "\" & oFlow.ProcessDef.Name & ".wmf"
            Unload oFlow
        End If
        oScan.FileList.Remove (1)
    Loop
    MsgBox "Image Export Complete", vbInformation
End Sub
Private Function loadProcess() As frmFlow
    dlg.Filter = "ACG Process Format|*.acgwfd.xml"
    dlg.FilterIndex = 1
    dlg.DialogTitle = "Load Process"
    '/dlg.FileName = Me.Caption
    dlg.Flags = MSComDlg.cdlOFNOverwritePrompt
    On Error Resume Next
    dlg.ShowOpen
    If Err.Number <> 0 Then Exit Function
    
    Set loadProcess = LoadFromFile(dlg.fileName)
End Function
Public Sub CommandLineLoadProcess(fileName As String)
    Dim oFlow As frmFlow
    Dim oDW As DocumentWindow
    
    Set oFlow = LoadFromFile(fileName)
    If Not (oFlow Is Nothing) Then
        Set oDW = ds.DocumentWindows.AddForm(CreateGUID, oFlow.getCaption, , oFlow, True)
    End If
End Sub
Private Function LoadFromFile(fileName As String, Optional showVersions As Boolean = True) As frmFlow
    Dim oFlow As frmFlow
    Set oFlow = New frmFlow
    oFlow.init moContainer, New ProcessTemplate, moTemplates, moProcessTemplates
    If Not oFlow.LoadFlow(fileName, showVersions) Then
        Unload oFlow
        Set oFlow = Nothing
    End If
    Set LoadFromFile = oFlow
End Function
Private Sub ds_DockWindowHide(ByVal DockWindow As InnovaDSXP.DockWindow, ByVal Reason As InnovaDSXP.VisibleStateChangedConstants)
    ds.Commands.GetToolButton("tl" & DockWindow.Name).State = dsxpCommandToolButtonStateUnchecked
End Sub

Private Sub ds_DockWindowShow(ByVal DockWindow As InnovaDSXP.DockWindow, ByVal Reason As InnovaDSXP.VisibleStateChangedConstants)
    ds.Commands.GetToolButton("tl" & DockWindow.Name).State = dsxpCommandToolButtonStateChecked
End Sub

Private Sub ds_DocumentWindowActivate(ByVal DocumentWindow As InnovaDSXP.DocumentWindow)
    Set moContextMenu = DocumentWindow.DocumentWindows.GetForm(DocumentWindow.Name).Form
    moContextMenu.Activate
End Sub

Private Sub ds_DocumentWindowDeactivate(ByVal DocumentWindow As InnovaDSXP.DocumentWindow)
    If Not (moContextMenu Is Nothing) Then
        moContextMenu.Deactivate
        Set moContextMenu = Nothing
    End If
    Dim oPropList As frmPropList
    
    Set oPropList = ds.DockWindows.GetForm("dwProperties").Form
    Set oPropList.PropBag = Nothing
    
    
End Sub

Private Sub ds_DocumentWindowHiding(ByVal DocumentWindow As InnovaDSXP.DocumentWindow, ByVal Reason As InnovaDSXP.VisibleStateChangedConstants, ByVal CancelDefault As InnovaDSXP.EventBoolean)
    Dim oContext As IContextMenu
    Dim fCancel As Boolean
    Set oContext = DocumentWindow.DocumentWindows.GetForm(DocumentWindow.Name).Form
    DocumentWindow.Activate
    oContext.QueryUnload fCancel
    CancelDefault = fCancel
End Sub

'/ application initialisation - this will be moved out of here at some point!
Private Sub Form_Load()
    On Error GoTo err_handler
    Const cstrFunc = "Form_Load"
    Dim strErrMsg As String
    
    Set moContainer = New Container
    Dim oDW As InnovaDSXP.DockWindowForm
    
    Dim oPalette As frmPalette
    strErrMsg = "Init Palette"
    With ds
        Set oDW = .DockWindows.Item("dwStepTypes")
        Set oPalette = New frmPalette
        Set oDW.Form = oPalette
    End With
   
    strErrMsg = "Load Palette"
    LoadPalette oPalette
    
    strErrMsg = "Init View Menu"
    
    Call InitViewMenu
    strErrMsg = "Init Proplist"
    
    Dim oPropList As frmPropList
    Set oPropList = New frmPropList
    Set oDW = ds.DockWindows("dwProperties")
    Set oDW.Form = oPropList
    
    Set oDW = ds.DockWindows("dwWarnings")
    
    '# removed for now as it does nothing!
    oDW.Delete
'    Dim oWarnings As frmWarnings
'    Set oWarnings = New frmWarnings
'    Set oDW.Form = oWarnings
'    With oWarnings
'        .AddWarning CreateGUID, "Screen", "Problem Test"
'        .AddWarning CreateGUID, "Routing", "Problem Test"
'        .AddWarning CreateGUID, "Activity", "Problem Test"
'        .AddWarning CreateGUID, "Decision", "Problem Test"
'        .AddWarning CreateGUID, "Split", "Problem Test"
'        .AddWarning CreateGUID, "Test", "Problem Test"
'    End With
    
    strErrMsg = "Load Process Templates"
    
    LoadProcessTemplates
    strErrMsg = "Load Addins"
    loadAddinMenus
Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc, strErrMsg)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub InitViewMenu()
    '/ creates menu items under the "view" menu for each of the tool windows
    Dim oCmd As InnovaDSXP.CommandToolButton
    Dim oDW As InnovaDSXP.DockWindow
    For Each oDW In ds.DockWindows
        Set oCmd = ds.Commands.AddToolButton("tl" & oDW.Name, oDW.Caption, , "View")
        oCmd.State = dsxpCommandToolButtonStateChecked
        oCmd.Tag = oDW.Name
        ds.Commands.GetPopupMenu("mnuView").CommandBar.Controls.Add oCmd.Name
    Next
End Sub

Private Sub Form_QueryUnload(Cancel As Integer, UnloadMode As Integer)
    Dim oDW As DocumentWindow
    Dim oContext As IContextMenu
    Dim fCancel As Boolean
    
    For Each oDW In ds.DocumentWindows
        Set oContext = oDW.DocumentWindows.GetForm(oDW.ID).Form
        oDW.Activate
        oContext.QueryUnload fCancel
        If fCancel Then Exit For
    Next
    Cancel = fCancel
End Sub

Private Sub moContainer_GetMe(oReturn As Object)
    Set oReturn = Me
End Sub

'/ converts all flows found in subfolders to the latest version of the workflow format
Private Sub BatchConvert()
    '# ZEBRA
    Const cstrFunc = "BatchConvert"
    Dim strErrMsg As String
    Dim oScanPath As ScanPath
    Dim strFileName As String
    Dim strDestPath As String
    Dim strSaveFile As String
    Dim oBrowse As clShellBrowse
    Dim strScanPath As String
    Dim strNewPath As String
    
    On Error GoTo err_handler
    Set oBrowse = New clShellBrowse
    With oBrowse
        .Caption = "Select path to convert"
        .Browse Me.hWnd
        If .Cancel Then Exit Sub
    End With
    strScanPath = oBrowse.Path
    With oBrowse
        .Caption = "Select path to put converted files"
        .Browse Me.hWnd
        If .Cancel Then Exit Sub
    End With
    
    strDestPath = oBrowse.Path
    Set oScanPath = New ScanPath
    
    oScanPath.StartScan strScanPath, ".acgwfd.xml"
    
    
    Dim oVersions As Versions
    
    Do Until oScanPath.FileList.Count = 0
        
        strFileName = oScanPath.FileList(1)
        oScanPath.FileList.Remove 1
        
        Set oVersions = loadProcessVers(strFileName)
    Loop

    MsgBox "Done"
Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc, "Flow: " & strErrMsg)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Function loadProcessVers(fileName As String, Optional destPath As String = vbNullString) As Versions
    On Error GoTo err_handler
    Const cstrFunc = "loadProcessVers"
    Dim fLoaded As Boolean
    Dim oVersions As New Versions
    Dim oLoad As XMLProcessVersion
    Dim strErrMsg As String
    strErrMsg = fileName
    
    Set oLoad = New XMLProcessVersion
    fLoaded = oLoad.FileLoadXML(fileName, oVersions, moTemplates, moProcessTemplates)
    
    If fLoaded Then
        Set loadProcessVers = oVersions
        Exit Function
    End If
        
    
    '/ try to convert the file
    Dim oProcessDef As ProcessDef
    Dim oFilter As XMLProcessDef
    
    Set oProcessDef = New ProcessDef
    Set oFilter = New XMLProcessDef
    fLoaded = oFilter.FileLoadXML(fileName, oProcessDef, moTemplates, moProcessTemplates)
    If fLoaded Then
        '/ add original GUID's as properties for conversion
        Call AddGUIDForConvert(oProcessDef)
    Else
        MsgBox "Failed to convert " & fileName, vbCritical
        Exit Function
    End If
    Dim strNewName As String
    If Len(destPath) = 0 Then
        oVersions.Add oProcessDef, 1
        Set loadProcessVers = oVersions
        Exit Function
    End If
    
    Debug.Print "converting " & fileName
    strNewName = OffsetPath(fileName, destPath)
    
    strErrMsg = strNewName
    
    If Len(Dir$(strNewName)) > 0 Then
        Kill strNewName
    End If
    
    MkDirExt strNewName
    oLoad.FileSaveXML strNewName, oVersions, oProcessDef
    Set oVersions = New Versions
    fLoaded = oLoad.FileLoadXML(strNewName, oVersions, moTemplates, moProcessTemplates)
    Set loadProcessVers = oVersions
    Exit Function
err_handler:
    Select Case reportError(Err, Me, cstrFunc, "Process: " & strErrMsg)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Function
    End Select
End Function

Private Function OffsetPath(fileName As String, NewPath As String) As String
    On Error GoTo err_handler:
    Dim intPos As Integer
    Dim intStart As Integer
    intStart = 1
    Dim strFileName As String
    
    Do
        intPos = InStr(intStart, fileName, "\")
        If intPos < 1 Then
            OffsetPath = Trim$(Left$(fileName, intStart))
            Exit Do
        End If
        If StrComp(Left$(fileName, intPos), Left$(NewPath, intPos)) <> 0 Then
            strFileName = Right$(fileName, Len(fileName) - InStrRev(fileName, "\"))
            OffsetPath = NewPath & "\" & strFileName
            Exit Function
        End If
        intStart = intPos + 1
        
    Loop
    
err_handler:
    Stop
    Resume 0
End Function

Private Sub MkDirExt(PathName As String)
    On Error GoTo err_handler:
    Dim intPos As Integer
    Dim intStart As Integer
    intStart = 1
    Do
        intPos = InStr(intStart, PathName, "\")
        If intPos < 1 Then Exit Do
        If Dir$(Left$(PathName, intPos) & "*.*", vbDirectory) = "" Then
            MkDir Left$(PathName, intPos)
        End If
        intStart = intPos + 1
    Loop
    Exit Sub
err_handler:
    Stop
    Resume 0
End Sub

Private Sub LoadPalette(oPalette As frmPalette)
    On Error GoTo err_handler
    Dim oTaskTemplateLoader As TaskTemplateLoader
    Dim oTaskTemplate As TaskTemplate
    Set oTaskTemplateLoader = New TaskTemplateLoader
    Dim strTemplatePath As String
    strTemplatePath = getTemplatePath()
    oTaskTemplateLoader.LoadTaskTemplates strTemplatePath & "tasks", moTemplates
    
    For Each oTaskTemplate In moTemplates
        oPalette.AddImage oTaskTemplate.Name, oTaskTemplate.Name, oTaskTemplate.Icon, oTaskTemplate.Description
    Next
   
    oPalette.Redraw
    Exit Sub
err_handler:
    stackError Err, Me, "loadPalette"
End Sub
Private Sub loadAddinMenus()
    On Error GoTo err_handler
    Dim XMLAddins As New XMLAddinLoader
    Set mAddins = XMLAddins.loadAddins(getTemplatePath() & "..\Addins")
    Dim cAddin As Addin
    Dim cmd As InnovaDSXP.Command
    For Each cAddin In mAddins
        Set cmd = ds.Commands.AddToolButton(cAddin.ClassName, cAddin.MenuName, , ds.Categories("Addins"))
        ds.Commands.GetPopupMenu("mnuAddins").CommandBar.Controls.Add cmd.ID
    Next
    Exit Sub
err_handler:
    stackError Err, Me, "loadAddinMenus"
End Sub
Private Sub LoadProcessTemplates()
    On Error GoTo err_handler
    Dim oXMLProcessTemplate As XMLProcessTemplate
    
    Set oXMLProcessTemplate = New XMLProcessTemplate
    
    Dim strTemplatePath As String
    
    strTemplatePath = getTemplatePath()
    If Not oXMLProcessTemplate.LoadTemplates(strTemplatePath & "processes", moProcessTemplates) Then
        MsgBox "Failed to load process templates", vbCritical
    End If
    Exit Sub
err_handler:
    stackError Err, Me, "loadProcessTemplates"
End Sub

Public Function getTemplatePath() As String
    Dim strTemplatePath As String
    
    Do
        strTemplatePath = GetSetting(App.Title, basMain.mcstrSettingSection, basMain.mcstrTemplatesPathKey, vbNullString)
        If Len(strTemplatePath) = 0 Then
            SaveSetting App.Title, basMain.mcstrSettingSection, basMain.mcstrTemplatesPathKey, App.Path & "\templates\"
        Else
            Exit Do
        End If
    Loop
    getTemplatePath = strTemplatePath
End Function
Private Sub MenuHandlerEdit(Command As InnovaDSXP.Command)
    Dim oPropWin As frmPropList
    Set oPropWin = ds.DockWindows.GetForm("dwProperties").Form
    On Error GoTo err_handler
    Select Case LCase$(Command.Name)
        Case "tlpropertyadd"
            frmPropertyAdd.AddProp oPropWin
            Unload frmPropertyAdd
        Case "tlpropertyremove"
            
    End Select
    '# ignore errors, like I care
err_handler:
    
End Sub

Private Sub combineVersions()
    On Error GoTo err_handler
    Const cstrFunc = "combineVersions"
    Dim pathBase As String
    Dim pathCombine As String
    Dim pathDest As String
    
    Dim Browse As New clShellBrowse
    Browse.Caption = "Select the path to the BASE Process Definitions - these files will act as the baseline for the combined files"
    Browse.Browse Me.hWnd
    If Browse.Cancel Then Exit Sub
    pathBase = Browse.Path
    
    Browse.Caption = "Select the path to the Process Definitions you want to COMBINE with the BASE - only the LATEST version from each file will be combined into the BASE"
    Browse.Browse Me.hWnd
    If Browse.Cancel Then Exit Sub
    pathCombine = Browse.Path
    
    Browse.Caption = "Select the DESTINATION for the COMBINED Process Definitions"
    Browse.Browse Me.hWnd
    If Browse.Cancel Then Exit Sub
    pathDest = Browse.Path
    
    Dim oBaseFiles As Collection
    Set oBaseFiles = loadProcessVersions(pathBase, pathDest)
    
    Dim oCombineFiles As Collection
    Set oCombineFiles = loadProcessVersions(pathCombine, pathDest)
    
    Dim oVersions As Versions
    Dim oProcessDef As ProcessDef
    Dim oBaseVersion As Versions
    
    For Each oVersions In oCombineFiles
        
        Set oProcessDef = oVersions.Item(oVersions.MaxVer).ProcessDef
        If Not existsInCol(oBaseFiles, oProcessDef.Name) Then
            '/ ensure base contains the new file
            Debug.Print "Adding " & oProcessDef.Name
            oBaseFiles.Add oVersions, oProcessDef.Name
        End If
    Next

    '/ now save all files
    
    Dim oSave As XMLProcessVersion
    Set oSave = New XMLProcessVersion
    Dim strFileName As String
    Dim oTaskDef As TaskDef
    
    For Each oVersions In oBaseFiles
        Set oProcessDef = oVersions.Item(oVersions.MaxVer).ProcessDef
        
        strFileName = pathDest & "\" & oProcessDef.Name & ".acgwfd.xml"
        
        If existsInCol(oCombineFiles, oProcessDef.Name) Then
            '/ add version from combinefiles
            Debug.Print "Adding new version to " & oProcessDef.Name
            
            Set oBaseVersion = oCombineFiles(oProcessDef.Name)
            Set oProcessDef = oBaseVersion.Item(oBaseVersion.MaxVer).ProcessDef
            For Each oTaskDef In oProcessDef.Tasks
                If oTaskDef.RoutingIn.Count = 0 Then
                    Set oProcessDef.FirstTask = oTaskDef
                    Exit For
                End If
            Next
        End If
        If Len(Dir$(strFileName)) = 0 Then
            On Error Resume Next
            FileCopy pathBase & "\" & oProcessDef.Name & ".acgwfd.xml", strFileName
            If Err.Number <> 0 Then
                FileCopy pathCombine & "\" & oProcessDef.Name & ".acgwfd.xml", strFileName
            End If
            On Error GoTo err_handler
        End If

        oSave.FileSaveXML strFileName, oVersions, oProcessDef
    Next

    MsgBox "Process Definitions combined!", vbInformation
    Exit Sub
err_handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Function loadProcessVersions(fromPath As String, Optional destConvertPath As String) As Collection
    On Error GoTo err_handler:
    Const cstrFunc = "loadProcessVersions"
    Dim oRtn As New Collection
    Dim oScan As ACGWFDHelper.ScanPath
    Dim strFileName As String
    Dim oVersions As Versions
    Dim strErrMsg As String
    Set oScan = New ScanPath
    oScan.StartScan fromPath, ".acgwfd.xml"
    Do Until oScan.FileList.Count = 0
        strFileName = oScan.FileList.Item(1)
        strErrMsg = strFileName
        oScan.FileList.Remove 1
        Set oVersions = loadProcessVers(strFileName, destConvertPath)
        oRtn.Add oVersions, oVersions.Item(oVersions.MaxVer).ProcessDef.Name
    Loop
    Set loadProcessVersions = oRtn
    Exit Function
err_handler:
    Select Case reportError(Err, Me, cstrFunc, "Process: " & strErrMsg)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Function
    End Select
End Function

Public Sub showPropGroupsPopup(oProperty As ACGProperties.Property)
    If oProperty Is Nothing Then Exit Sub
    Dim ofrmFlow As frmFlow
    Set ofrmFlow = moContextMenu
    Dim btn As CommandToolButton
    Set btn = ds.Commands.Item("tlPropertyRemove")
    With btn
        .Caption = "Remove " & oProperty.Name
        .Enabled = ofrmFlow.canRemoveProp(oProperty)
    End With
    ds.Commands.GetPopupMenu("mnuPropGroupsPopup").ShowPopup
End Sub
'/ return true if the user changed the task type
Public Function changeTaskType(oTaskDef As TaskDef) As Boolean
    changeTaskType = frmChangeTaskType.changeTaskType(oTaskDef, Me, moTemplates)
    Unload frmChangeTaskType
End Function
