VERSION 5.00
Object = "{BA5F9142-B708-4B5E-93B0-3948F8003F86}#1.2#0"; "PropertyGridControl.ocx"
Begin VB.Form frmPropList 
   Caption         =   "Form1"
   ClientHeight    =   3195
   ClientLeft      =   60
   ClientTop       =   345
   ClientWidth     =   2550
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   Icon            =   "frmPropList.frx":0000
   LinkTopic       =   "Form1"
   ScaleHeight     =   3195
   ScaleWidth      =   2550
   StartUpPosition =   3  'Windows Default
   Begin ACGPropGrid.PropertyGrid pg 
      Height          =   2055
      Left            =   360
      TabIndex        =   0
      Top             =   300
      Width           =   1335
      _ExtentX        =   2355
      _ExtentY        =   3625
   End
End
Attribute VB_Name = "frmPropList"
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
Private Const mcstrModule As String = "frmPropList"
Private mPropBag As PropertyGroup
Public Event PropChanged(oProperty As Property)
Private moParent As Container
Private moTaskTemplates As TaskTemplates
Private moProcessTemplates As ProcessTemplates
Private Property Get MDI() As frmMDI
    Set MDI = moParent.getParent
End Property
Private Sub Form_Resize()
    On Error Resume Next
    pg.Move 0, 0, ScaleWidth, ScaleHeight
End Sub
Public Sub init(oParent As Container, oTaskTemplates As TaskTemplates, oProcessTemplates As ProcessTemplates)
    Set moParent = oParent
    Set moTaskTemplates = oTaskTemplates
    Set moProcessTemplates = oProcessTemplates
End Sub

Public Property Set PropBag(v As PropertyGroup)
    Dim oProp As Property
    'ZEBRA
    'pg.Commit
    Set mPropBag = v
    'pg.Clear
    Set pg.PropertyGroup = mPropBag
    If mPropBag Is Nothing Then Exit Property
'    With pg
'        For Each oProp In mPropBag
'            .AddItem oProp.Name, oProp.Value
'        Next
'    End With
End Property

Private Sub pg_ContextClick(oProperty As ACGProperties.Property, X As Single, y As Single)
    MDI.showPropGroupsPopup oProperty
End Sub

Private Sub pg_FileBrowse(oProperty As ACGProperties.Property, fileName As String, Cancel As Boolean)
    Const cstrFunc = "pg_FileBrowse"
    On Error GoTo Err_Handler
    
    Dim dlg As MSComDlg.CommonDialog
    Dim oLoad As XMLProcessVersion
    Set dlg = MDI.dlg
    dlg.Filter = "ACG WorkFlow Format|*.acgwfd.xml"
    dlg.filterIndex = 1
    dlg.dialogTitle = "Set SubProcess"
    dlg.fileName = Me.Caption
    dlg.Flags = MSComDlg.cdlOFNOverwritePrompt
    On Error Resume Next
    dlg.ShowOpen
    If Err.Number <> 0 Then
        Cancel = True
        Exit Sub
    End If
    On Error GoTo Err_Handler
    Set oLoad = New XMLProcessVersion
    Dim oVersions As Versions
    Set oVersions = New Versions
    Dim oProcessDef As ProcessDef
    fileName = dlg.fileName
    If Not oLoad.FileLoadXML(fileName, oVersions, moTaskTemplates, moProcessTemplates) Then
        '/ try the old loader
        Dim oImport As XMLProcessDef
        Set oImport = New XMLProcessDef
        Set oProcessDef = New ProcessDef
        If Not (oImport.FileLoadXML(fileName, oProcessDef, moTaskTemplates, moProcessTemplates)) Then
            MsgBox "Failed to load process!", vbExclamation
            Cancel = True
            Exit Sub
        End If
        If MsgBox("Process was from an older version. Convert?", vbYesNo + vbQuestion) = vbNo Then
            MsgBox "Failed to load process!", vbExclamation
            Cancel = True
            Exit Sub
        End If
        oProcessDef.PropertyGroup.Item("(General)").Item("Name").Locked = True
        Kill fileName
        oLoad.FileSaveXML fileName, oVersions, oProcessDef
    Else
        Set oProcessDef = oVersions(oVersions.MaxVer).ProcessDef
    End If
    fileName = oProcessDef.Name
    '# copy Input and Output property sections
    Dim oPropsSrc As Properties, oPropsDest As Properties
    
    Set oPropsSrc = oProcessDef.PropertyGroup("(Inputs)")
    Set oPropsDest = oProperty.Properties.PropertyGroup(oPropsSrc.Name)
    
    CopyProps oPropsSrc, oPropsDest, True, False, True
    
    Set oPropsSrc = oProcessDef.PropertyGroup("(Outputs)")
    Set oPropsDest = oProperty.Properties.PropertyGroup(oPropsSrc.Name)
    
    CopyProps oPropsSrc, oPropsDest, True, True, True
    pg.Refresh
    Exit Sub
Err_Handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select

End Sub

Private Sub pg_PropChanged(oProperty As Property)
    On Error GoTo Err_Handler
    'mPropBag.Item(Name).Value = Value
    RaiseEvent PropChanged(oProperty)
    Exit Sub
Err_Handler:
    'mPropBag.Add Name, Value
End Sub

Private Sub pg_PropRemoved(oProperty As Property)
    Const cstrFunc = "pg_PropRemoved"
    On Error GoTo Err_Handler
    'mPropBag.Remove Name
    Exit Sub
Err_Handler:
    Select Case reportError(Err, Me, cstrFunc)
        Case vbIgnore
            Resume Next
        Case vbRetry
            Resume 0
        Case Else
            Exit Sub
    End Select
End Sub

Private Sub pg_TextPopup(oProperty As ACGProperties.Property, Cancel As Boolean)
    On Error Resume Next
    Load frmTextPopup
    If frmTextPopup.doTextPopup(oProperty) Then
        oProperty.Value = Trim$(frmTextPopup.Text)
        Cancel = False
    Else
        Cancel = True
    End If
    Unload frmTextPopup
    
End Sub
