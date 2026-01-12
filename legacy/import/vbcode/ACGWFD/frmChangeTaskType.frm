VERSION 5.00
Begin VB.Form frmChangeTaskType 
   BorderStyle     =   3  'Fixed Dialog
   Caption         =   "Change Task Type"
   ClientHeight    =   4995
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   4995
   ControlBox      =   0   'False
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   MaxButton       =   0   'False
   MinButton       =   0   'False
   ScaleHeight     =   4995
   ScaleWidth      =   4995
   ShowInTaskbar   =   0   'False
   StartUpPosition =   1  'CenterOwner
   Begin VB.CheckBox chkEraseMisMatched 
      Caption         =   "Remove extraneous Properties"
      Height          =   495
      Left            =   180
      TabIndex        =   4
      Top             =   3720
      Value           =   1  'Checked
      Width           =   4575
   End
   Begin VB.ListBox lstTT 
      Height          =   2985
      Left            =   120
      TabIndex        =   3
      Top             =   600
      Width           =   4755
   End
   Begin VB.CommandButton cmdCancel 
      Cancel          =   -1  'True
      Caption         =   "Cancel"
      Height          =   495
      Left            =   3660
      TabIndex        =   2
      Top             =   4380
      Width           =   1215
   End
   Begin VB.CommandButton cmdOK 
      Caption         =   "OK"
      Height          =   495
      Left            =   120
      TabIndex        =   1
      Top             =   4380
      Width           =   1215
   End
   Begin VB.Label lblCurrent 
      Caption         =   "lblCurrent"
      Height          =   315
      Left            =   120
      TabIndex        =   0
      Top             =   120
      Width           =   4755
   End
End
Attribute VB_Name = "frmChangeTaskType"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit
Private mfCancel As Boolean
Private moTaskDef As TaskDef
Private moTaskTemplates As TaskTemplates
Private Sub cmdCancel_Click()
    mfCancel = True
    Me.Hide
End Sub
    
    
Private Sub cmdOK_Click()
    If chkEraseMisMatched.Value = vbChecked Then
        If Not doEraseCheck Then
            Exit Sub
        End If
    End If
    mfCancel = False
    Me.Hide
End Sub

Public Function changeTaskType(oTaskDef As TaskDef, oParent As frmMDI, oTemplates As TaskTemplates) As Boolean
    
    Dim oTT As TaskTemplate
    lstTT.Clear
    Dim intIndex As Integer
    
    For Each oTT In oTemplates
        lstTT.AddItem oTT.Name
        If oTT.Name = oTaskDef.TaskTemplate Then
            intIndex = lstTT.NewIndex
        End If
    Next
    Set moTaskDef = oTaskDef
    Set moTaskTemplates = oTemplates
    lstTT.ListIndex = intIndex
    Me.Show vbModal, oParent
    changeTaskType = Not mfCancel
    If mfCancel Then Exit Function
    Set oTT = oTemplates(lstTT.List(lstTT.ListIndex))
    Dim colErased As Collection
    If chkEraseMisMatched.Value = vbChecked Then
        eraseMisMatched oTaskDef, oTT, oTemplates(oTaskDef.TaskTemplate)
    End If
    oTaskDef.TaskTemplate = oTT.Name
    CopyPropGroup oTT.PropertyGroup, oTaskDef.PropertyGroup
End Function
Private Function doEraseCheck() As Boolean
    Dim colErased As Collection
    Set colErased = eraseMisMatched(moTaskDef, moTaskTemplates(lstTT.List(lstTT.ListIndex)), moTaskTemplates(moTaskDef.TaskTemplate), True)
    Dim strMsg As String
    Dim p As Property
    For Each p In colErased
        If Not p.Locked Then
            If p.Value > "" Then
                strMsg = strMsg & "(" & p.Properties.Name & ") " & p.Name & " = " & p.Value & vbCrLf
            End If
        End If
    Next
    If strMsg > "" Then
        doEraseCheck = (MsgBox("The following properties and values will be REMOVED if you continue with this operation" & vbCrLf & strMsg & "Are you sure?", vbQuestion Or vbYesNo Or vbDefaultButton2) = vbYes)
    Else
        doEraseCheck = True
    End If
End Function
'/ erase properties from the taskdef where they exist in TTOLD but not in TTNEW
Private Function eraseMisMatched(oTaskDef As TaskDef, oTTNew As TaskTemplate, oTTOld As TaskTemplate, Optional dontErase As Boolean = False) As Collection
    Dim props As Properties
    Dim p As Property
    Dim colErase As Collection
    Set colErase = New Collection
    Dim fRemove As Boolean
    For Each props In oTTOld.PropertyGroup
        For Each p In props
            If Not oTTNew.PropertyGroup.Exists(props.Name) Then
                fRemove = True
            ElseIf Not oTTNew.PropertyGroup(props.Name).Exists(p.Name) Then
                fRemove = True
            Else
                fRemove = False
            End If
            If fRemove Then
                colErase.Add oTaskDef.PropertyGroup(props.Name)(p.Name)
                If Not dontErase Then
                    oTaskDef.PropertyGroup(props.Name).Remove p.Name
                End If
            End If
        Next
    Next
    Set eraseMisMatched = colErase
End Function
