VERSION 5.00
Begin VB.Form frmFind 
   BorderStyle     =   3  'Fixed Dialog
   Caption         =   "Find"
   ClientHeight    =   1350
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   3840
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   Icon            =   "frmFind.frx":0000
   LinkTopic       =   "Form1"
   MaxButton       =   0   'False
   MinButton       =   0   'False
   ScaleHeight     =   1350
   ScaleWidth      =   3840
   ShowInTaskbar   =   0   'False
   StartUpPosition =   3  'Windows Default
   Begin VB.ComboBox cboMatchType 
      Height          =   315
      ItemData        =   "frmFind.frx":0E42
      Left            =   900
      List            =   "frmFind.frx":0E4C
      Style           =   2  'Dropdown List
      TabIndex        =   1
      Top             =   840
      Width           =   1455
   End
   Begin VB.TextBox txtFind 
      Height          =   285
      Left            =   240
      TabIndex        =   0
      Top             =   360
      Width           =   2115
   End
   Begin VB.CommandButton cmdClose 
      Cancel          =   -1  'True
      Caption         =   "&Close"
      Height          =   495
      Left            =   2520
      TabIndex        =   3
      Top             =   720
      Width           =   1215
   End
   Begin VB.CommandButton cmdFind 
      Caption         =   "&Find"
      Default         =   -1  'True
      Enabled         =   0   'False
      Height          =   495
      Left            =   2520
      TabIndex        =   2
      Top             =   120
      Width           =   1215
   End
   Begin VB.Label lbl 
      AutoSize        =   -1  'True
      Caption         =   "Matching:"
      Height          =   195
      Index           =   1
      Left            =   120
      TabIndex        =   5
      Top             =   900
      Width           =   705
   End
   Begin VB.Label lbl 
      AutoSize        =   -1  'True
      Caption         =   "Find What:"
      Height          =   195
      Index           =   0
      Left            =   120
      TabIndex        =   4
      Top             =   120
      Width           =   795
   End
End
Attribute VB_Name = "frmFind"
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
Private mFlowGUI As AddFlow4Lib.AddFlow
'/ counter used for "find next"
Private mlngNode As Long
'/ counter used for "find next"
Private mlngLink As Long

Private mfFindNext As Boolean
Private mfMatchedNode As Boolean


Public Property Set Flow(v As AddFlow4Lib.AddFlow)
    Set mFlowGUI = v
    mfFindNext = False
    cboMatchType.ListIndex = 0
End Property

Private Sub cmdClose_Click()
    mfFindNext = False
    Unload Me
End Sub

Private Sub cmdFind_Click()
    
    Dim oNode As AddFlow4Lib.afNode
    Dim oLink As AddFlow4Lib.afLink
    Dim lngNode As Long
    Dim lngLink As Long
    Dim fFound As Boolean
    
    
    If Not mfFindNext Then
        mlngLink = 1
        mlngNode = 1
        mfMatchedNode = False
    Else
        mlngLink = mlngLink + 1
    End If
    
    Do Until mlngNode > mFlowGUI.Nodes.Count
    
        Set oNode = mFlowGUI.Nodes(mlngNode)
        
        If Not mfMatchedNode Then
            
            If cboMatchType.List(cboMatchType.ListIndex) = "Partial" Then
                fFound = InStr(1, oNode.Text, txtFind, vbTextCompare) > 0
            Else
                fFound = StrComp(oNode.Text, txtFind, vbTextCompare) = 0
            End If
            
            If fFound Then
                '# found item
                mfFindNext = True
                UnselectAll
                oNode.Selected = True
                oNode.EnsureVisible
                mfMatchedNode = True
                Exit Sub
            End If
        End If
        
        Do Until mlngLink > oNode.OutLinks.Count
            
            Set oLink = oNode.OutLinks(mlngLink)
            If cboMatchType.List(cboMatchType.ListIndex) = "Partial" Then
                fFound = InStr(1, oLink.Text, txtFind, vbTextCompare) > 0
            Else
                fFound = StrComp(oLink.Text, txtFind, vbTextCompare) = 0
            End If
            If fFound Then
                '# found item
                mfFindNext = True
                UnselectAll
                oLink.Selected = True
                oLink.EnsureVisible
                Exit Sub
            End If
            mlngLink = mlngLink + 1
        Loop
        mlngLink = 1
        mlngNode = mlngNode + 1
        mfMatchedNode = False
    Loop
    If mfFindNext Then
        MsgBox "No more matches"
    Else
        MsgBox "Text not found"
    End If
    mfFindNext = False
End Sub

Private Sub Form_Unload(Cancel As Integer)
    Set mFlowGUI = Nothing
End Sub

Private Sub UnselectAll()
    mFlowGUI.SelNodes.Clear
    mFlowGUI.SelLinks.Clear
End Sub

Private Sub txtFind_Change()
    cmdFind.Enabled = Len(txtFind) > 0
    mfFindNext = False
End Sub
